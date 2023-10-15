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
        self,
        epsilon: float = None,
        slide_range: bool = None,
        thresh: float = None,
        **kwargs: dict(),
    ) -> None:
        allowed_params = {"epsilon", "slide_range", "thresh"}

        epsilon_value = locals().get("epsilon")
        if epsilon_value is None:
            raise ValueError("Epsilon is a required parameter for Synthesizer.")
        if not isinstance(epsilon_value, (int, float)):
            raise TypeError(
                f"Epsilon must be of type int or float, got {type(epsilon_value).__name__}."
            )
        self.epsilon = float(epsilon_value)
        self.range_transform = None
        self.data = None

        for param in kwargs.keys():
            if param not in allowed_params:
                raise ValueError(
                    f"Parameter '{param}' is not available for this type of synthesizer."
                )

        param_defaults = {"slide_range": (False, bool), "thresh": (0.05, float)}

        for param, (default_value, param_type) in param_defaults.items():
            param_value = locals().get(param)
            if param_value is not None:
                if isinstance(param_value, int) and param_type is float:
                    param_value = float(param_value)
                if not isinstance(param_value, param_type):
                    raise TypeError(
                        f"{param} must be of type {param_type.__name__}, got {type(param_value).__name__}."
                    )
                setattr(self, param, param_value)
            else:
                setattr(self, param, default_value)

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
        epsilon: float = None,
        slide_range: bool = None,
        thresh: float = None,
        preprocess_factor: float = None,
        delta: float = None,
        verbose: bool = None,
        **synth_kwargs: dict()
    ) -> None:
        super().__init__(epsilon, slide_range, thresh)

        allowed_additional_params = {"preprocess_factor", "delta", "verbose"}
        for param in synth_kwargs.keys():
            if param not in allowed_additional_params:
                raise ValueError(
                    f"Parameter '{param}' is not available for this type of synthesizer."
                )

        param_defaults = {
            "preprocess_factor": (0.05, float),
            "delta": (1e-09, float),
            "verbose": (False, bool),
        }

        for param, (default_value, param_type) in param_defaults.items():
            param_value = locals().get(param)
            if param_value is not None:
                if isinstance(param_value, int) and param_type is float:
                    param_value = float(param_value)
                if not isinstance(param_value, param_type):
                    raise TypeError(
                        f"{param} must be of type {param_type.__name__}, got {type(param_value).__name__}."
                    )
                setattr(self, param, param_value)
            else:
                setattr(self, param, default_value)

        self.synthesizer = SmartnoiseMSTSynthesizer(epsilon=self.epsilon, **synth_kwargs)

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
        epsilon: float = None,
        slide_range: bool = None,
        thresh: float = None,
        preprocess_factor: float = None,
        **synth_kwargs: dict()
    ):
        super().__init__(epsilon, slide_range, thresh)
        allowed_additional_params = {"preprocess_factor"}
        for param in synth_kwargs.keys():
            if param not in allowed_additional_params:
                raise ValueError(
                    f"Parameter '{param}' is not available for this type of synthesizer."
                )

        preprocess_factor_value = locals().get("preprocess_factor")
        if preprocess_factor_value is not None:
            if isinstance(preprocess_factor_value, int):
                preprocess_factor_value = float(preprocess_factor_value)
            if not isinstance(preprocess_factor_value, float):
                raise TypeError(
                    f"preprocess_factor must be of type float, got {type(preprocess_factor_value).__name__}."
                )
            self.preprocess_factor = preprocess_factor_value
        else:
            self.preprocess_factor = 0.05

        self.synthesizer = PytorchDPSynthesizer(
            epsilon=self.epsilon,
            gan=SmartnoisePATECTGAN(epsilon=self.epsilon),
            **synth_kwargs,
        )

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
        epsilon: float = None,
        slide_range: bool = None,
        thresh: float = None,
        privbayes_limit: int = None,
        privbayes_bins: int = None,
        temp_files_dir: str = None,
        seed: int = None,
        **synth_kwargs: dict()
    ) -> None:
        super().__init__(epsilon, slide_range, thresh)

        allowed_additional_params = {
            "privbayes_limit",
            "privbayes_bins",
            "temp_files_dir",
            "seed",
        }
        for param in synth_kwargs.keys():
            if param not in allowed_additional_params:
                raise ValueError(
                    f"Parameter '{param}' is not available for this type of synthesizer."
                )

        param_defaults = {
            "privbayes_limit": (20, int),
            "privbayes_bins": (10, int),
            "temp_files_dir": ("temp", str),
            "seed": (0, int),
        }

        for param, (default_value, param_type) in param_defaults.items():
            param_value = locals().get(param)
            if param_value is not None:
                if isinstance(param_value, int) and param_type is float:
                    param_value = float(param_value)
                if not isinstance(param_value, param_type):
                    raise TypeError(
                        f"{param} must be of type {param_type.__name__}, got {type(param_value).__name__}."
                    )
                setattr(self, param, param_value)
            else:
                setattr(self, param, default_value)

        self.describer = DataDescriber(category_threshold=self.privbayes_limit)
        self.generator = DataGenerator()

        os.makedirs(self.temp_files_dir, exist_ok=True)
        self.candidate_keys = {"index": True}
        self.dataset_size = None

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
        self,
        epsilon: float = None,
        slide_range: bool = None,
        thresh: float = None,
        **synth_kwargs: dict()
    ):
        super().__init__(epsilon, slide_range, thresh, **synth_kwargs)
        self.synthesizer = AggregateSeededSynthesizer(
            epsilon=self.epsilon,
            percentile_percentage=99,
            reporting_length=3,
            **synth_kwargs,
        )

    def fit(self, df: pd.DataFrame):
        df = self._slide_range(df)
        self.synthesizer.fit(df, transformer=NoTransformer())

    def sample(self, n):
        df = self.synthesizer.sample(n)
        df = self._unslide_range(df)
        return df


class AIMTSynthesizer(Synthesizer):
    """
    Synthesizer which uses AIM: An Adaptive and Iterative Mechanism

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

    """
    def __init__(
        self,
        epsilon: float = None,
        slide_range: bool = None,
        thresh: float = None,
        **synth_kwargs: dict()
    ):
        super().__init__(epsilon, slide_range, thresh, **synth_kwargs)
        self.synthesizer = SmartnoiseAIMSynthesizer(
            epsilon=self.epsilon, **synth_kwargs
        )

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
    """
    Synthesizer which uses AIM: An Adaptive and Iterative Mechanism with adjustable
    `rounds_factor` parameter to influence the number of rounds to run the mechanism.

    ----------
    Parameters
        epsilon : float
            privacy budget for the synthesizer
        rounds_factor : float = 0.1
            the factor to determine the number of rounds to run the AIM mechanism
            before generating the synthetic dataset.
    -----------
    Optional keyword arguments:
        slide_range : bool = False
            specifies if the slide range transformation should be applied, this will 
            make the minimal value of each column 0 before fitting.
        thresh : float = 0.05
            specifies what the ratio of unique values to the column length should be for
            the column to be threated as cathegorical

    """
    def __init__(
        self,
        epsilon: float = None,
        slide_range: bool = None,
        thresh: float = None,
        rounds_factor: float = None,
        **synth_kwargs: dict()
    ):
        super().__init__(epsilon, slide_range, thresh)

        allowed_additional_params = {"rounds_factor"}
        for param in synth_kwargs.keys():
            if param not in allowed_additional_params:
                raise ValueError(
                    f"Parameter '{param}' is not available for this type of synthesizer."
                )

        rounds_factor_value = locals().get("rounds_factor")
        if rounds_factor_value is not None:
            if isinstance(rounds_factor_value, int):
                rounds_factor_value = float(rounds_factor_value)
            if not isinstance(rounds_factor_value, float):
                raise TypeError(
                    f"preprocess_factor must be of type float, got {type(rounds_factor_value).__name__}."
                )
            self.rounds_factor = rounds_factor_value
        else:
            self.rounds_factor = 0.1

        self.synthesizer = SmartnoiseAIMSynthesizer(epsilon=self.epsilon, rounds_factor=self.rounds_factor)

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
    def __init__(
        self,
        epsilon: float = None,
        slide_range: bool = None,
        thresh: float = None,
        k: int = None,
        T: int = None,
        recycle: bool = None,
        verbose: bool = None,
        **synth_kwargs: dict()
    ):
        super().__init__(epsilon, slide_range, thresh)

        allowed_additional_params = {"k", "T", "recycle", "verbose"}
        for param in synth_kwargs.keys():
            if param not in allowed_additional_params:
                raise ValueError(
                    f"Parameter '{param}' is not available for this type of synthesizer."
                )

        param_defaults = {
            "k": (3, int),
            "T": (100, int),
            "recycle": (True, bool),
            "verbose": (False, bool),
        }

        for param, (default_value, param_type) in param_defaults.items():
            param_value = locals().get(param)
            if param_value is not None:
                if isinstance(param_value, int) and param_type is float:
                    param_value = float(param_value)
                if not isinstance(param_value, param_type):
                    raise TypeError(
                        f"{param} must be of type {param_type.__name__}, got {type(param_value).__name__}."
                    )
                setattr(self, param, param_value)
            else:
                setattr(self, param, default_value)

        self.synth_kwargs = synth_kwargs
        self.device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    
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