import os
import json
import pandas as pd
import numpy as np

from snsynth.mst import MSTSynthesizer
from snsynth.preprocessors import GeneralTransformer, BaseTransformer
from snsynth.pytorch import PytorchDPSynthesizer
from snsynth.pytorch.nn import PATECTGAN

from DataSynthesizer.DataDescriber import DataDescriber
from DataSynthesizer.DataGenerator import DataGenerator


class PrivateDataGenerator():
    """
    Central data privatizer - generates private data
    in proper folder architecture given a Publication.
    """
    EPSILONS = [(np.e ** -1, 'e^-1'), 
            (np.e ** 0, 'e^0'), 
            (np.e ** 1, 'e^1'),
            (np.e ** 2, 'e^2')]

    ITERATIONS = 5

    # Add a json domain file for each paper here, MST requirement.
    DOMAINS = {
        "saw2018cross": "domains/saw2018cross-domain.json",
        "jeong2021math": "domains/jeong2021math-domain.json",
        "fairman2019marijuana": "domains/fairman2019marijuana-domain.json",
        "fruiht2018naturally": "domains/fruiht2018naturally-domain.json",
    }

    def __init__(self, publication):
        self.publication = publication
        self.cont_features = publication.cont_features

    def prepare_dataframe(self):
        df = self.publication.dataframe
        print(df.apply(lambda x: x.unique()))
        print(df.apply(lambda x: len(x.unique())))
        return df
    
    def generate(self):
        df = self.prepare_dataframe()

        df_map = {
            self.publication.DEFAULT_PAPER_ATTRIBUTES['id'] : df
        }

        temp_files_dir = 'temp'
        os.makedirs(temp_files_dir, exist_ok=True)
        df.to_csv(os.path.join(temp_files_dir, "temp.csv"))

        for pub_name, df in df_map.items():
            print('Generating: ' + pub_name)
            if not os.path.exists('private_data/' + str(pub_name)):
                os.mkdir('private_data/' + str(pub_name))
            for (eps, str_eps) in self.EPSILONS:
                print(f'EPSILON: {str_eps}...')

                if not os.path.exists('private_data/' + str(pub_name) + '/' + str_eps):
                    os.mkdir('private_data/' + str(pub_name) + '/' + str_eps)

                for it in range(self.ITERATIONS):
                    print(f'ITERATION: {it}...')

                    # Folder for deposit
                    folder_name = 'private_data/' + str(pub_name) + '/' + str_eps + '/'
                    
                    if not os.path.isfile(folder_name + 'mst_' + str(it) + '.pickle'):
                        # The MST Synthesis
                        mst = MSTSynthesizer(epsilon=eps,
                                             domain=pub_name, 
                                             domains_dict=self.DOMAINS)
                        mst.fit(df)
                        sample_size = len(df)
                        mst_synth_data = mst.sample(sample_size)
                        mst_synth_data.to_pickle(folder_name + 'mst_' + str(it) + '.pickle')
                        print(mst_synth_data.apply(lambda x: x.unique()))
                        print(mst_synth_data.apply(lambda x: len(x.unique())))

                    print('DONE: MST.')

                    if not os.path.isfile(folder_name + 'patectgan_' + str(it) + '.pickle'):
                        # The PATECTGAN Synthesis
                        preprocess_factor = 0.1
                        patectgan = PytorchDPSynthesizer(eps, 
                                                        PATECTGAN(preprocessor_eps=(preprocess_factor * eps)), 
                                                        preprocessor=None)
                        patectgan.fit(
                            df,
                            categorical_columns=list(df.columns),
                            transformer=BaseTransformer,
                        )
                        sample_size = len(df)
                        patectgan_synth_data = patectgan.sample(sample_size)
                        patectgan_synth_data.to_pickle(folder_name + 'patectgan_' + str(it) + '.pickle')
                        print(patectgan_synth_data.apply(lambda x: x.unique()))
                        print(patectgan_synth_data.apply(lambda x: len(x.unique())))

                    print('DONE: PATECTGAN.')

                    if not os.path.isfile(folder_name + 'privbayes_' + str(it) + '.pickle'):
                        # The PrivBayes Synthesis

                        # specify which attributes are candidate keys of input dataset.
                        candidate_keys = {'index': True}

                        # An attribute is categorical if its domain size is less than this threshold.
                        # Here modify the threshold to adapt to the domain size of "education" (which is 14 in input dataset).
                        threshold_value = 40

                        domain_name = self.DOMAINS[pub_name]
                        with open(domain_name) as json_file:
                            dict_domain = json.load(json_file)

                        # temp for PrivBayes to show there are cont values
                        if self.cont_features:
                            for cont_feature in self.cont_features:
                                dict_domain[cont_feature] = threshold_value + 1

                        # specify categorical attributes
                        categorical_attributes = {k: True for k, v in dict_domain.items() if v < threshold_value}
                        
                        # Intialize a describer and a generator
                        describer = DataDescriber(category_threshold=threshold_value)
                        describer.describe_dataset_in_correlated_attribute_mode(f"{temp_files_dir}/temp.csv",
                                                                                epsilon=eps, 
                                                                                k=2,
                                                                                attribute_to_is_categorical=categorical_attributes,
                                                                                attribute_to_is_candidate_key=candidate_keys,
                                                                                seed=np.random.randint(1000000))
                        describer.save_dataset_description_to_file(f"{temp_files_dir}/privbayes_description.csv")

                        generator = DataGenerator()
                        generator.generate_dataset_in_correlated_attribute_mode(len(df),
                                                                                f"{temp_files_dir}/privbayes_description.csv")
                        generator.save_synthetic_data(f"{temp_files_dir}/privbayes_synth.csv")
                        privbayes_synth_data = pd.read_csv(f"{temp_files_dir}/privbayes_synth.csv")
                        privbayes_synth_data.to_pickle(folder_name + 'privbayes_' + str(it) + '.pickle')
                        print(privbayes_synth_data.apply(lambda x: x.unique()))
                        print(privbayes_synth_data.apply(lambda x: len(x.unique())))

                    print('DONE: PrivBayes.')


if __name__ == '__main__':
    from papers import Fairman2019Marijuana, Jeong2021Math

    for p in [Jeong2021Math]:
        # epsilon -> percent_soft_findings
        pub_id = p.DEFAULT_PAPER_ATTRIBUTES['id']
        pub_file_base_df = p.DEFAULT_PAPER_ATTRIBUTES['base_dataframe_pickle']

        p_base_instantiated = p(filename=pub_file_base_df)
        data_generator = PrivateDataGenerator(p_base_instantiated)

        # In case data has not already been generated
        data_generator.generate()
