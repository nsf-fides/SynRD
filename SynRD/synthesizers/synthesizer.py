import logging
import os
from abc import ABC, abstractmethod

import pickle

import pandas as pd
import numpy as np
import torch

from DataSynthesizer.DataDescriber import DataDescriber
from DataSynthesizer.DataGenerator import DataGenerator
from snsynth.aggregate_seeded import AggregateSeededSynthesizer
from snsynth.mst import MSTSynthesizer as SmartnoiseMSTSynthesizer
from snsynth.pytorch import PytorchDPSynthesizer
from snsynth.pytorch.nn import PATECTGAN as SmartnoisePATECTGAN
from SynRD.synthesizers.controllable_aim import SmartnoiseAIMSynthesizer
from snsynth.transform import NoTransformer
from snsynth.transform.table import TableTransformer

from src.qm import KWayMarginalQMTorch
from src.syndata import NeuralNetworkGenerator
from src.algo import IterAlgoSingleGEM as GEM
from src.utils import Dataset, Domain
from src.qm.qm import KWayMarginalQMTorch
from src.syndata import NeuralNetworkGenerator
from src.algo import IterAlgoSingleGEM as GEM
from src.utils import get_rand_workloads

logger = logging.getLogger(__name__)


class Synthesizer(ABC):
    def __init__(
        self, epsilon: float, slide_range: bool = True, thresh=0.05, synth_kwargs=dict()
    ):
        self.data = None
        self.epsilon = epsilon
        self.slide_range = slide_range
        self.range_transform = None
        self.thresh = thresh

    @abstractmethod
    def fit(self, df: pd.DataFrame) -> None:
        raise NotImplementedError

    @abstractmethod
    def sample(self, n) -> pd.DataFrame:
        raise NotImplementedError

    def load(self, file_path):
        return pd.read_pickle(file_path)

    def save(self, data, base_dir):
        file_path = os.path.join(
            base_dir, type(self).__name__ + str(self.epsilon) + ".pickle"
        )
        data.to_pickle(file_path)

    def _slide_range(self, df):
        if self.slide_range:
            df, self.range_transform = self.slide_range_forward(df)
        return df

    def _unslide_range(self, df):
        if self.slide_range and self.range_transform is None:
            raise ValueError("Must fit synthesizer before sampling.")
        if self.slide_range:
            df = self.slide_range_backward(df, self.range_transform)
        return df

    def _categorical_continuous(self, df):
        # NOTE: return categorical/ordinal columns and continuous
        # This is slightly hacky, but should be fine.
        categorical = []
        continuous = []
        for col in df.columns:
            if (float(df[col].nunique()) / df[col].count()) < self.thresh:
                categorical.append(col)
            else:
                continuous.append(col)
        return {"categorical": categorical, "continuous": continuous}

    @staticmethod
    def slide_range_forward(df):
        transform = {}
        for c in df.columns:
            if min(df[c]) > 0:
                transform[c] = min(df[c])
                df[c] = df[c] - min(df[c])
        return df, transform

    @staticmethod
    def slide_range_backward(df, transform) -> pd.DataFrame:
        for c in df.columns:
            if c in transform:
                df[c] = df[c] + transform[c]
        return df


class MSTSynthesizer(Synthesizer):
    """
    MST: Maximum Spanning Tree synthesizer.

    ----------
    Parameters
        epsilon : float
            privacy budget for the synthesizer
    -----------
    Optional keyword arguments:
        slide_range : bool = False
            specifies if the slide range transformation should be applied, this will 
            make the minimal value of each column 0 before fitting.
        thresh : float = 0.05
            specifies what the ratio of unique values to the column length should be for
            the column to be threated as cathegorical
        preprocess_factor : float = 0.05
            amount of budget to be used for the data preprocessing
        delta : float = 1e-09
            privacy parameter, should be small, in the range of 1/(n * sqrt(n))
        verbose: bool = False
            print diagnostic information during processing
    """
    def __init__(
        self,
        epsilon: float,
        slide_range: bool = False,
        thresh=0.05,
        preprocess_factor: float = 0.05,
        synth_kwargs=dict(),
    ):
        self.synthesizer = SmartnoiseMSTSynthesizer(epsilon=epsilon, **synth_kwargs)
        self.preprocess_factor = preprocess_factor
        super().__init__(epsilon, slide_range, thresh, synth_kwargs)

    def fit(self, df: pd.DataFrame):
        categorical_check = len(self._categorical_continuous(df)["categorical"]) == len(
            list(df.columns)
        )
        if not categorical_check:
            raise ValueError(
                "Please make sure that MST gets categorical/ordinal\
                features only. If you are sure you only passed categorical, \
                increase the `thresh` parameter."
            )

        df = self._slide_range(df)
        self.synthesizer.fit(
            df, preprocessor_eps=(self.preprocess_factor * self.epsilon)
        )

    def sample(self, n):
        df = self.synthesizer.sample(n)
        df = self._unslide_range(df)
        return df


class PATECTGAN(Synthesizer):
    """
    Conditional tabular GAN using Private Aggregation of Teacher Ensembles

    ----------
    Parameters
        epsilon : float
            privacy budget for the synthesizer
    -----------
    Optional keyword arguments:
        slide_range : bool = False
            specifies if the slide range transformation should be applied, this will 
            make the minimal value of each column 0 before fitting.
        thresh : float = 0.05
            specifies what the ratio of unique values to the column length should be for
            the column to be threated as cathegorical
        preprocess_factor : float = 0.05
            amount of budget to be used for the data preprocessing

    """
    def __init__(
        self,
        epsilon: float,
        slide_range: bool = False,
        preprocess_factor: float = 0.05,
        thresh=0.05,
        synth_kwargs=dict(),
    ):
        self.preprocess_factor = preprocess_factor
        self.synthesizer = PytorchDPSynthesizer(
            epsilon=epsilon, gan=SmartnoisePATECTGAN(epsilon=epsilon), **synth_kwargs
        )

        super().__init__(epsilon, slide_range, thresh)

    def fit(self, df: pd.DataFrame):
        df = self._slide_range(df)
        cat_con = self._categorical_continuous(df)
        self.synthesizer.fit(
            df,
            categorical_columns=cat_con["categorical"],
            continuous_columns=cat_con["continuous"],
            preprocessor_eps=(self.preprocess_factor * self.epsilon),
        )

    def sample(self, n):
        df = self.synthesizer.sample(n)
        df = self._unslide_range(df)
        return df


class PrivBayes(Synthesizer):
    """
    Synthesizer which uses bayesian approach.

    ----------
    Parameters
        epsilon : float
            privacy budget for the synthesizer
        slide_range : bool = False
            specifies if the slide range transformation should be applied, this will 
            make the minimal value of each column 0 before fitting.
    -----------
    Optional keyword arguments:
        thresh : float = 0.05
            specifies what the ratio of unique values to the column length should be for
            the column to be threated as cathegorical
        privbayes_limit : int = 20
            if number of unique values in the column exceeds this limit, it will be binned
        privbayes_bins : int = 10
            number of bins (if binning is happening)
        temp_files_dir : str = 'temp'
            directory used to save the file produced by the data describer
        seed : int = 0
            random seed to be used

    """
    def __init__(
        self,
        epsilon: float,
        slide_range: bool,
        thresh=0.05,
        privbayes_limit=20,
        privbayes_bins=10,
        temp_files_dir="temp",
        seed=0,
        synth_kwargs=dict(),
    ) -> None:
        self.privbayes_limit = privbayes_limit
        self.privbayes_bins = privbayes_bins
        self.temp_files_dir = temp_files_dir
        self.seed = seed

        self.describer = DataDescriber(category_threshold=self.privbayes_limit)
        self.generator = DataGenerator()

        os.makedirs(self.temp_files_dir, exist_ok=True)
        self.candidate_keys = {"index": True}
        self.dataset_size = None
        super().__init__(epsilon, slide_range, thresh)

    def fit(self, df: pd.DataFrame):
        df = self._slide_range(df)

        # NOTE: PrivBayes implementation has some weird requirements
        # as it runs so slowly when data is high dimensional
        # Here, we check to see whether we need to bin data
        binned = {}
        for col in df.columns:
            if len(df[col].unique()) > self.privbayes_limit:
                col_df = pd.qcut(df[col], q=self.privbayes_bins, duplicates="drop")
                df[col] = col_df.apply(lambda row: row.mid).astype(int)
                binned[col] = True

        cat_con = self._categorical_continuous(df)
        categorical_check = len(cat_con["categorical"]) == len(list(df.columns))
        if not categorical_check:
            raise ValueError(
                "PrivBayes does not work with continous columns. Suggest \
                decreasing the `privbayes_limit` or increasing the `thresh` parameter."
            )

        df.to_csv(os.path.join(self.temp_files_dir, "temp.csv"))
        self.dataset_size = len(df)
        self.describer.describe_dataset_in_correlated_attribute_mode(
            f"{self.temp_files_dir}/temp.csv",
            epsilon=self.epsilon,
            k=2,
            attribute_to_is_categorical=binned,
            attribute_to_is_candidate_key=self.candidate_keys,
            seed=self.seed,
        )
        self.describer.save_dataset_description_to_file(
            f"{self.temp_files_dir}/privbayes_description.csv"
        )

    def sample(self, n):
        self.generator.generate_dataset_in_correlated_attribute_mode(
            n, f"{self.temp_files_dir}/privbayes_description.csv"
        )
        self.generator.save_synthetic_data(f"{self.temp_files_dir}/privbayes_synth.csv")
        df = pd.read_csv(f"{self.temp_files_dir}/privbayes_synth.csv", index_col=0)

        df = self._unslide_range(df)
        return df


class PacSynth(Synthesizer):
    def __init__(
        self, epsilon: float, slide_range: bool, thresh=0.05, synth_kwargs=dict()
    ):
        self.synthesizer = AggregateSeededSynthesizer(
            epsilon=epsilon,
            percentile_percentage=99,
            reporting_length=3,
            **synth_kwargs,
        )
        super().__init__(epsilon, slide_range, thresh)

    def fit(self, df: pd.DataFrame):
        df = self._slide_range(df)
        self.synthesizer.fit(df, transformer=NoTransformer())

    def sample(self, n):
        df = self.synthesizer.sample(n)
        df = self._unslide_range(df)
        return df


class AIMTSynthesizer(Synthesizer):
    def __init__(
        self,
        epsilon: float,
        slide_range: bool = False,
        thresh=0.05,
        synth_kwargs=dict(),
    ):
        self.synthesizer = SmartnoiseAIMSynthesizer(epsilon=epsilon, **synth_kwargs)
        super().__init__(epsilon, slide_range, thresh)

    def fit(self, df: pd.DataFrame):
        categorical_check = len(self._categorical_continuous(df)["categorical"]) == len(
            list(df.columns)
        )
        if not categorical_check:
            raise ValueError(
                "Please make sure that AIM gets categorical/ordinal\
                features only. If you are sure you only passed categorical, \
                increase the `thresh` parameter."
            )

        df = self._slide_range(df)
        self.synthesizer.fit(df)

    def sample(self, n):
        df = self.synthesizer.sample(n)
        df = self._unslide_range(df)
        return df

class AIMSynthesizer(Synthesizer):
    def __init__(self, 
                 epsilon: float, 
                 slide_range: bool = False,
                 thresh = 0.05,
                 rounds_factor = 0.1):
        self.synthesizer = SmartnoiseAIMSynthesizer(epsilon=epsilon, rounds_factor=rounds_factor)
        super().__init__(epsilon, slide_range, thresh)

    def fit(self, df: pd.DataFrame):
        categorical_check = (len(self._categorical_continuous(df)['categorical']) == len(list(df.columns)))
        if not categorical_check:
            raise ValueError('Please make sure that AIM gets categorical/ordinal\
                features only. If you are sure you only passed categorical, \
                increase the `thresh` parameter.')

        df = self._slide_range(df)
        self.synthesizer.fit(df)

    def sample(self, n):
        df = self.synthesizer.sample(n)
        df = self._unslide_range(df)
        return df


class GEMSynthesizer(Synthesizer):
    def __init__(self, epsilon: float, 
                 slide_range: bool = False, 
                 thresh=0.05, 
                 k=3,
                 T=100,
                 recycle=True,
                 synth_kwargs=dict(), 
                 verbose=False):
        self.synth_kwargs = synth_kwargs
        self.verbose = verbose
        self.k = k
        self.T = T
        self.recycle = recycle

        self.device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
        super().__init__(epsilon, slide_range, thresh)
    
    def _get_train_data(self, data, *ignore, style, transformer, categorical_columns, ordinal_columns, continuous_columns, nullable, preprocessor_eps):
        if transformer is None or isinstance(transformer, dict):
            self._transformer = TableTransformer.create(data, style=style,
                categorical_columns=categorical_columns,
                continuous_columns=continuous_columns,
                ordinal_columns=ordinal_columns,
                nullable=nullable,
                constraints=transformer)
        elif isinstance(transformer, TableTransformer):
            self._transformer = transformer
        else:
            raise ValueError("transformer must be a TableTransformer object, a dictionary or None.")
        if not self._transformer.fit_complete:
            if self._transformer.needs_epsilon and (preprocessor_eps is None or preprocessor_eps == 0.0):
                raise ValueError("Transformer needs some epsilon to infer bounds.  If you know the bounds, pass them in to save budget.  Otherwise, set preprocessor_eps to a value > 0.0 and less than the training epsilon.  Preprocessing budget will be subtracted from training budget.")
            self._transformer.fit(
                data,
                epsilon=preprocessor_eps
            )
            eps_spent, _ = self._transformer.odometer.spent
            if eps_spent > 0.0:
                self.epsilon -= eps_spent
                print(f"Spent {eps_spent} epsilon on preprocessor, leaving {self.epsilon} for training")
                if self.epsilon < 10E-3:
                    raise ValueError("Epsilon remaining is too small!")
        train_data = self._transformer.transform(data)
        return train_data

    def fit(self, 
            df: pd.DataFrame,
            *ignore,
            transformer=None,
            categorical_columns=[],
            ordinal_columns=[],
            continuous_columns=[],
            preprocessor_eps=0.0,
            nullable=False,):
        
        if type(df) is pd.DataFrame:
            self.original_column_names = df.columns
        
        categorical_check = (len(self._categorical_continuous(df)['categorical']) == len(list(df.columns)))
        if not categorical_check:
            raise ValueError('Please make sure that RAP gets categorical/ordinal\
                features only. If you are sure you only passed categorical, \
                increase the `thresh` parameter.')
        df = self._slide_range(df)

        train_data = self._get_train_data(
            df,
            style='cube',
            transformer=transformer,
            categorical_columns=categorical_columns,
            ordinal_columns=ordinal_columns,
            continuous_columns=continuous_columns,
            nullable=nullable,
            preprocessor_eps=preprocessor_eps
        )

        if self._transformer is None:
            raise ValueError("We weren't able to fit a transformer to the data. Please check your data and try again.")

        cards = self._transformer.cardinality
        if any(c is None for c in cards):
            raise ValueError("The transformer appears to have some continuous columns. Please provide only categorical or ordinal.")

        dimensionality = np.prod(cards)
        if self.verbose:
            print(f"Fitting with {dimensionality} dimensions")
            print(self._transformer.output_width)

        colnames = ["col" + str(i) for i in range(self._transformer.output_width)]

        if len(cards) != len(colnames):
            raise ValueError("Cardinality and column names must be the same length.")

        domain = Domain(colnames, cards)
        data = pd.DataFrame(train_data, columns=colnames)
        data = Dataset(df=data, domain=domain)
        workloads = get_rand_workloads(data, 100000, self.k)

        self.query_manager_torch = KWayMarginalQMTorch(data, workloads, verbose=True, device=self.device)
        true_answers_torch = self.query_manager_torch.get_answers(data)

        self.G = NeuralNetworkGenerator(self.query_manager_torch, K=1000, device=self.device, init_seed=0,
                           embedding_dim=512, gen_dims=None, resample=False)
        
        self.algo = GEM(self.G, self.T, self.epsilon,
           alpha=0.67, default_dir=None, verbose=True, seed=0,
           loss_p=2, lr=1e-4, max_idxs=100, max_iters=100,
           ema_weights=True, ema_weights_beta=0.9)

        self.algo.fit(true_answers_torch)

    def sample(self, n):
        assert self.G is not None, "Please fit the synthesizer first."
        syndata = self.G.get_syndata(num_samples=n)
        df = self._unslide_range(syndata.df)
        return df