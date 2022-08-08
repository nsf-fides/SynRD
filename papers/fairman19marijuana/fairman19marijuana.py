from papers.meta_classes import Publication, Finding
from papers.meta_classes import NonReproducibleFindingException
from papers.file_utils import PathSearcher
import pandas as pd
import numpy as np
import os


class Fairman19Marijuana(Publication):
    DEFAULT_PAPER_ATTRIBUTES = {
        'id': 'fairman19marijuana',
        'length_pages': 16,
        'authors': ['Brian J Fairman', 'C Debra Furr-Holden', 'Renee M Johnson'],
        'journal': 'Prevention Science',
        'year': 2019,
        'current_citations': 39,
        'base_dataframe_pickle': 'fairman19marijuana_dataframe.pickle'
    }
    DATAFRAME_COLUMNS = ['YEAR', 'CLASS', 'SEX', 'RACE', 'AGE_GROUP', 'AGE', 'MINAGE']
    INPUT_FILES = [
        'data/32722-0001-Data.tsv', 'data/23782-0001-Data.tsv', 'data/04596-0001-Data.tsv',
        'data/26701-0001-Data.tsv', 'data/29621-0001-Data.tsv', 'data/36361-0001-Data.tsv',
        'data/35509-0001-Data.tsv', 'data/04373-0001-Data.tsv', 'data/21240-0001-Data.tsv',
        'data/34481-0001-Data.tsv', 'data/34933-0001-Data.tsv'
    ]
    INPUT_FIELDS = ['NEWRACE', 'AGE','IRSEX', 'USEACM', 'CIGTRY', 'ALCTRY', 'MJAGE', 'CIGARTRY', 'CHEWTRY', 'SNUFTRY',
                    'SLTTRY', 'COCAGE', 'HALLAGE', 'HERAGE', 'INHAGE', 'ANALAGE', 'SEDAGE', 'STIMAGE', 'TRANAGE']
    FILE_YEAR_MAP = {f: 2004 + i for i, f in enumerate(sorted([os.path.basename(f) for f in INPUT_FILES]))}
    CLASS_MAP = class_mapping = {
        'MARIJUANA': 'MARIJUANA',
        'MJAGE': 'MARIJUANA',
        'ALCOHOL': 'ALCOHOL',
        'ALCTRY': 'ALCOHOL',
        'CIGARETTES': 'CIGARETTES',
        'CIGTRY': 'CIGARETTES',
        'NO_DRUG_USE': 'NO_DRUG_USE',
        'NOUSAGE': 'NO_DRUG_USE',
        'OTHER_TABACCO': 'OTHER_TABACCO',
        'CIGARTRY': 'OTHER_TABACCO',
        'SNUFTRY': 'OTHER_TABACCO',
        'CHEWTRY': 'OTHER_TABACCO',
        'SLTTRY': 'OTHER_TABACCO',
        'OTHER_DRUGS': 'OTHER_DRUGS',
        'HERAGE': 'OTHER_DRUGS',
        'COCAGE': 'OTHER_DRUGS',
        'SEDAGE': 'OTHER_DRUGS',
        'STIMAGE': 'OTHER_DRUGS',
        'TRANAGE': 'OTHER_DRUGS',
        'INHAGE': 'OTHER_DRUGS',
        'ANALAGE': 'OTHER_DRUGS',
        'HALLAGE': 'OTHER_DRUGS'
    }
    AGE_GROUP_MAP = {
        12: '12-13', 13: '12-13', 14: '14-15', 15: '14-15', 16: '16-17', 17: '16-17', 18: '18-19', 19: '18-19',
        20: '20-21', 21: '20-21'
    }
    RACE_MAP = {1: 'White', 2: 'Black', 3: 'AI/AN', 4: 'NHOPI', 5: 'Asian', 6: 'Multi-racial', 7: 'Hispanic'}
    USE_ACM_MAP = {
        1: 'ALCTRY', 2: 'CIGTRY', 3: 'MJAGE', 4: 'ALCTRY', 5: 'CIGTRY', 6: 'MJAGE', 91: 'NOUSAGE',
    }
    CLASSES = ['CIGTRY', 'ALCTRY', 'MJAGE', 'CIGARTRY', 'CHEWTRY', 'SNUFTRY', 'SLTTRY', 'COCAGE', 'HALLAGE', 'HERAGE',
               'INHAGE', 'ANALAGE', 'SEDAGE', 'STIMAGE', 'TRANAGE']

    def __init__(self, dataframe=None, filename=None, path=None):
        if dataframe is None:
            if path is None:
                path = self.DEFAULT_PAPER_ATTRIBUTES['id']
            self.path_searcher = PathSearcher(path)
            if filename is None:
                filename = self.DEFAULT_PAPER_ATTRIBUTES['base_dataframe_pickle']
            try:
                dataframe = pd.read_pickle(self.path_searcher.get_path(filename))
            except FileNotFoundError:
                dataframe = self._recreate_dataframe()
        super().__init__(dataframe)
        self.FINDINGS = self.FINDINGS + [
            Finding(self.finding_5_1),
            Finding(self.finding_5_2),
            Finding(self.finding_5_3),
            Finding(self.finding_5_4),
            Finding(self.finding_5_5),
            Finding(self.finding_5_6),
            Finding(self.finding_5_7),
            Finding(self.finding_5_8),
            Finding(self.finding_5_9),
            Finding(self.finding_5_10),
            Finding(self.finding_6_1),
            Finding(self.finding_6_2),
        ]

    def _merge_input_files(self):
        dfs = []
        for file in self.INPUT_FILES:
            df_n1 = pd.read_csv(file, sep='\t', skipinitialspace=True, nrows=1)
            current_columns = []
            for field in self.INPUT_FIELDS:
                field = field.strip()
                if field in df_n1.columns:
                    current_columns.append(field)
                elif f'{field}2' in df_n1.columns:
                    current_columns.append(f'{field}2')
                else:
                    print(f'field {field} not in {file}')
            current_columns += ['CIGTRY']
            df = pd.read_csv(file, sep='\t', skipinitialspace=True, usecols=current_columns)
            df['file_name'] = os.path.basename(file)
            dfs.append(df)
        return pd.concat(dfs)

    def _recreate_dataframe(self, filename='fairman19marijuana_dataframe.pickle'):
        main_df = self._merge_input_files()
        main_df = main_df[(main_df['AGE2'] < 11)]  # filter people < 22 yo
        main_df['MINAGE'] = main_df[self.CLASSES].values.min(axis=1)
        main_df['MINAGE'] = np.where(main_df['MINAGE'] > 900, 999, main_df['MINAGE'])
        main_df['MINAGE_CLASS'] = np.where(main_df['MINAGE'] > 900, 'NO_DRUG_USE', None)
        main_df['CLASSES_LIST'] = np.where(main_df['MINAGE'] > 900, 'NO_DRUG_USE', None)
        main_df = main_df[
            ~(main_df.MINAGE_CLASS == 'NO_DRUG_USE') == (main_df.USEACM == 99)]  # remove where unknown class
        main_df['YEAR'] = main_df['file_name'].map(self.FILE_YEAR_MAP)  # infer year
        main_df['SEX'] = main_df['IRSEX'].map({1: 'Male', 2: 'Female'})
        main_df['AGE'] = main_df['AGE2'].map({i: i + 11 for i in range(1, 11)})
        main_df['RACE'] = main_df['NEWRACE2'].map(self.RACE_MAP)
        main_df['AGE_GROUP'] = main_df['AGE'].map(self.AGE_GROUP_MAP)
        main_df.reset_index(inplace=True, drop=True)
        for i, row in main_df.iterrows():
            if row['MINAGE'] > 900:  # used smth
                continue
            several_substances = sorted(
                row[self.CLASSES][row[self.CLASSES].apply(lambda x: x == row['MINAGE'])].index.values)
            several_substances_mapped = sorted(list(set([self.CLASS_MAP[s] for s in several_substances])))
            main_df.at[i, 'CLASSES_LIST'] = '/'.join(several_substances_mapped)
            if len(several_substances_mapped) == 1:
                main_df.at[i, 'MINAGE_CLASS'] = several_substances_mapped[0]
            else:
                main_df.at[i, 'MINAGE_CLASS'] = self.USE_ACM_MAP.get(row['USEACM']) or np.random.choice(
                    several_substances_mapped)
        main_df['CLASS'] = main_df['MINAGE_CLASS'].map(self.CLASS_MAP)
        main_df.reset_index(inplace=True, drop=True)
        # main_df['AGE_GROUP'] = main_df['AGE'].map(self.AGE_GROUP_MAP)
        main_df.reset_index(inplace=True, drop=True)
        main_df['SEX'] = main_df['SEX'].astype('category')
        main_df['RACE'] = main_df['RACE'].astype('category')
        # main_df['AGE_GROUP'] = main_df['AGE_GROUP'].astype('category')
        main_df['CLASS'] = main_df['CLASS'].astype('category')
        main_df['YEAR'] = main_df['YEAR'].astype('category')
        main_df['AGE'] = main_df['AGE'].astype(np.int32)
        main_df['MINAGE'] = main_df['MINAGE'].astype(np.int32)
        df = main_df[self.DATAFRAME_COLUMNS]
        print(df.columns)
        df.to_pickle(filename)
        return df

    def finding_5_1(self):
        """
        For each substance, the mean age of reported first use increased over the study period.
        The mean age of first marijuana use increased ( 0.5 years)  from 14.7 years in 2004 to 15.2 years in 2014;.
        """
        mean_first_marijuana_use_2004 = self.dataframe[
            (self.dataframe.CLASS == 'MARIJUANA') & (self.dataframe.YEAR == 2004)]['MINAGE'].mean()
        mean_first_marijuana_use_2014 = self.dataframe[
            (self.dataframe.CLASS == 'MARIJUANA') & (self.dataframe.YEAR == 2014)]['MINAGE'].mean()
        age_diff = np.round(mean_first_marijuana_use_2014 - mean_first_marijuana_use_2004, 1)
        findings = [mean_first_marijuana_use_2004, mean_first_marijuana_use_2014]
        soft_findings = [mean_first_marijuana_use_2014 > mean_first_marijuana_use_2004]
        hard_findings = [np.allclose(age_diff, 0.5, atol=10e-2)]
        return findings, soft_findings, hard_findings

    def finding_5_2(self):
        """
        these numbers were comparable to those for age of first use of cigarettes (13.6 vs. 15.0; 1.4 years)
        """
        mean_age_first_use_2004 = self.dataframe[
            (self.dataframe.CLASS == 'CIGARETTES') & (self.dataframe.YEAR == 2004)]['MINAGE'].mean()
        mean_age_first_use_2014 = self.dataframe[
            (self.dataframe.CLASS == 'CIGARETTES') & (self.dataframe.YEAR == 2014)]['MINAGE'].mean()
        age_diff = np.round(mean_age_first_use_2014 - mean_age_first_use_2004, 2)
        findings = [mean_age_first_use_2004, mean_age_first_use_2014]
        soft_findings = [mean_age_first_use_2014 > mean_age_first_use_2004]
        hard_findings = [np.allclose(age_diff, 1.4, atol=10e-2)]
        return findings, soft_findings, hard_findings

    def finding_5_3(self):
        """
        alcohol (14.4 vs. 15.2;  0.8 years)
        """
        mean_age_first_use_2004 = self.dataframe[
            (self.dataframe.CLASS == 'ALCOHOL') & (self.dataframe.YEAR == 2004)]['MINAGE'].mean()
        mean_age_first_use_2014 = self.dataframe[
            (self.dataframe.CLASS == 'ALCOHOL') & (self.dataframe.YEAR == 2014)]['MINAGE'].mean()
        age_diff = np.round(mean_age_first_use_2014 - mean_age_first_use_2004, 1)
        findings = [mean_age_first_use_2004, mean_age_first_use_2014]
        soft_findings = [mean_age_first_use_2014 > mean_age_first_use_2004]
        hard_findings = [np.allclose(age_diff, 0.8, atol=10e-2)]
        return findings, soft_findings, hard_findings

    def finding_5_4(self):
        """
        other tobacco (14.8 vs. 15.7;  0.9 years)
        """
        mean_age_first_use_2004 = self.dataframe[
            (self.dataframe.CLASS == 'OTHER_TABACCO') & (self.dataframe.YEAR == 2004)]['MINAGE'].mean()
        mean_age_first_use_2014 = self.dataframe[
            (self.dataframe.CLASS == 'OTHER_TABACCO') & (self.dataframe.YEAR == 2014)]['MINAGE'].mean()
        age_diff = np.round(mean_age_first_use_2014 - mean_age_first_use_2004, 1)
        findings = [mean_age_first_use_2004, mean_age_first_use_2014]
        soft_findings = [mean_age_first_use_2014 > mean_age_first_use_2004]
        hard_findings = [np.allclose(age_diff, 0.9, atol=10e-2)]
        return findings, soft_findings, hard_findings

    def finding_5_5(self):
        """
        and other drug use (14.4 vs. 15.0;  0.6 years)
        """
        mean_age_first_use_2004 = self.dataframe[
            (self.dataframe.CLASS == 'OTHER_DRUGS') & (self.dataframe.YEAR == 2004)]['MINAGE'].mean()
        mean_age_first_use_2014 = self.dataframe[
            (self.dataframe.CLASS == 'OTHER_DRUGS') & (self.dataframe.YEAR == 2014)]['MINAGE'].mean()
        age_diff = np.round(mean_age_first_use_2014 - mean_age_first_use_2004, 1)
        findings = [mean_age_first_use_2004, mean_age_first_use_2014]
        soft_findings = [mean_age_first_use_2014 > mean_age_first_use_2004]
        hard_findings = [np.allclose(age_diff, 0.6, atol=10e-2)]
        return findings, soft_findings, hard_findings

    def finding_5_6(self):
        """
        Aggregated across survey years, 5.8% of respondents reported that they initiated marijuana before other substances,
        compared to 29.8% for alcohol, 14.2% for cigarettes, 3.6% for other tobacco products, and 5.9% other drugs
        (these data are provided in online supplemental Table S1)
        """
        table = self.dataframe.CLASS.value_counts()/self.dataframe.shape[0]
        marijuana_ratio = table['MARIJUANA'] * 100
        alcohol_ratio = table['MARIJUANA'] * 100
        cigarettes_ratio = table['MARIJUANA'] * 100
        other_tobacco_ratio = table['MARIJUANA'] * 100
        other_drugs_ratio = table['MARIJUANA'] * 100
        findings = [marijuana_ratio, alcohol_ratio, cigarettes_ratio, other_drugs_ratio, other_tobacco_ratio]
        hard_findings = [np.allclose(marijuana_ratio, 5.8, atol=10e-2), np.allclose(alcohol_ratio, 29.8, atol=10e-2),
            np.allclose(cigarettes_ratio, 14.2, atol=10e-2), np.allclose(other_drugs_ratio, 5.9, atol=10e-2),
            np.allclose(other_tobacco_ratio, 3.6, atol=10e-2)]
        return findings, [], hard_findings

    def finding_5_7(self):
        """
        From 2004 to 2014, the proportion who had initiated marijuana before other substances increased
        from 4.4% to 8.0% (Figure 1), declined for those having initiated cigarettes first (21.4% to 8.9%)
        and increased in youth having abstained from substance use (35.5% to 46.3%)
        """
        marijuana_prop_2004 = self.dataframe[(self.dataframe.CLASS == 'MARIJUANA') & (self.dataframe.YEAR == 2004)
                                             ].shape[0] * 100 / self.dataframe[ (self.dataframe.YEAR == 2004)].shape[0]
        marijuana_prop_2014 = self.dataframe[(self.dataframe.CLASS == 'MARIJUANA') & (self.dataframe.YEAR == 2014)
                                             ].shape[0] * 100 / self.dataframe[ (self.dataframe.YEAR == 2014)].shape[0]
        cig_prop_2004 = self.dataframe[(self.dataframe.CLASS == 'CIGARETTES') & (self.dataframe.YEAR == 2004)
                                       ].shape[0] * 100 / self.dataframe[ (self.dataframe.YEAR == 2004)].shape[0]
        cig_prop_2014 = self.dataframe[(self.dataframe.CLASS == 'CIGARETTES') & (self.dataframe.YEAR == 2014)
                                       ].shape[0] * 100 / self.dataframe[ (self.dataframe.YEAR == 2014)].shape[0]
        no_usage_prop_2004 = self.dataframe[(self.dataframe.CLASS == 'NO_DRUG_USE') & (self.dataframe.YEAR == 2004)
                                       ].shape[0] * 100 / self.dataframe[(self.dataframe.YEAR == 2004)].shape[0]
        no_usage_prop_2014 = self.dataframe[(self.dataframe.CLASS == 'NO_DRUG_USE') & (self.dataframe.YEAR == 2014)
                                       ].shape[0] * 100/ self.dataframe[(self.dataframe.YEAR == 2014)].shape[0]
        findings = [marijuana_prop_2004, marijuana_prop_2014, cig_prop_2004, cig_prop_2014,
                    no_usage_prop_2004, no_usage_prop_2014]
        soft_findings = [marijuana_prop_2004 < marijuana_prop_2014, cig_prop_2004 > cig_prop_2014,
                         no_usage_prop_2004 < no_usage_prop_2014]
        hard_findings = [np.allclose(marijuana_prop_2004, 4.4, atol=10e-2), np.allclose(marijuana_prop_2014, 8.0, atol=10e-2),
                         np.allclose(cig_prop_2004, 21.4, atol=10e-2), np.allclose(cig_prop_2014, 8.9, atol=10e-2),
                         np.allclose(no_usage_prop_2004, 35.5, atol=10e-2), np.allclose(no_usage_prop_2014, 46.3, atol=10e-2)]
        return findings, soft_findings, hard_findings

    def table_s1(self, feature):
        return self.dataframe[['CLASS', feature]].value_counts() / self.dataframe[[feature]].value_counts()

    def finding_5_8(self):
        """
        Males were more likely than females to have initiated marijuana first (7.1%) or other tobacco products first (5.7%),
        """
        table = self.table_s1(feature='SEX')
        male_marijuana_ratio = table['Male', 'MARIJUANA'] * 100
        female_marijuana_ratio = table['Female', 'MARIJUANA'] * 100
        male_other_tobacco_ratio = table['Male', 'OTHER_TABACCO'] * 100
        female_other_tobacco_ratio = table['Female', 'OTHER_TABACCO'] * 100
        findings = [male_marijuana_ratio, male_other_tobacco_ratio]
        soft_findings = [male_marijuana_ratio > female_marijuana_ratio, male_other_tobacco_ratio > female_other_tobacco_ratio]
        hard_findings = [np.allclose(male_marijuana_ratio, 7.1, atol=10e-2),
                         np.allclose(male_other_tobacco_ratio,  5.7, atol=10e-2)]
        return findings, soft_findings, hard_findings

    def finding_5_9(self):
        """
        whereas females were more likely than males to have initiated cigarettes (15.2%) or alcohol first (32.0%)
        """
        table = self.table_s1(feature='SEX')
        male_cigarettes_ratio = table['Male', 'CIGARETTES'] * 100
        female_cigarettes_ratio = table['Female', 'CIGARETTES'] * 100
        male_alcohol_ratio = table['Male', 'ALCOHOL'] * 100
        female_alcohol_ratio = table['Female', 'ALCOHOL'] * 100
        findings = [female_cigarettes_ratio, female_alcohol_ratio]
        soft_findings = [male_cigarettes_ratio < female_cigarettes_ratio, male_alcohol_ratio < female_alcohol_ratio]
        hard_findings = [np.allclose(female_cigarettes_ratio, 15.2, atol=10e-2),
                         np.allclose(female_alcohol_ratio,  32.0, atol=10e-2)]
        return findings, soft_findings, hard_findings

    def finding_5_10(self):
        """
        Considering age, a small proportion of 12–13-year-olds (0.6%) reported initiating marijuana before other substances,
        """
        table = self.table_s1(feature='AGE_GROUP')
        youngest_marijuana_ratio = table['12-13', 'MARIJUANA'] * 100
        hard_findings = [np.allclose(youngest_marijuana_ratio, 0.6, atol=10e-2)]
        return [youngest_marijuana_ratio], [], hard_findings

    def finding_6_1(self):
        """
        but by ages 18–19 and 20–21-years this proportion increased to 9.1% and 9.4%, respectively.
        """
        table = self.table_s1(feature='AGE_GROUP')
        youngest_marijuana_ratio = table['12-13', 'MARIJUANA'] * 100
        high_school_grads_marijuana_ratio = table['18-19', 'MARIJUANA'] * 100
        oldest_marijuana_ratio = table['20-21', 'MARIJUANA'] * 100
        soft_findings = [high_school_grads_marijuana_ratio > youngest_marijuana_ratio,
                         oldest_marijuana_ratio > youngest_marijuana_ratio]
        hard_findings = [np.allclose(high_school_grads_marijuana_ratio, 9.1, atol=10e-2),
                         np.allclose(oldest_marijuana_ratio, 9.4, atol=10e-2)]
        return [youngest_marijuana_ratio], soft_findings, hard_findings

    def finding_6_2(self):
        """
        American Indian/Alaskan Native (AI/AN) (11.8%) and Black youth (9.4%) had the highest proportion of initiating
        marijuana first; White (4.6%) and Asian youth (2.5% had the lowest).
        """
        table = self.table_s1(feature='RACE')
        aian_marijuana_ratio = table['AI/AN', 'MARIJUANA'] * 100
        black_marijuana_ratio = table['Black', 'MARIJUANA'] * 100
        white_marijuana_ratio = table['White', 'MARIJUANA'] * 100
        asian_marijuana_ratio = table['Asian', 'MARIJUANA'] * 100
        all_marijuana_sorted = sorted([table[race, 'MARIJUANA'] * 100 for race in self.dataframe.RACE.unique()])
        soft_findings = [sorted(all_marijuana_sorted[-2:]) == sorted([aian_marijuana_ratio, black_marijuana_ratio]),
                         sorted(all_marijuana_sorted[:2]) == sorted([white_marijuana_ratio, asian_marijuana_ratio])]
        hard_findings = [np.allclose(aian_marijuana_ratio, 11.8, atol=10e-2),
                         np.allclose(black_marijuana_ratio, 9.4, atol=10e-2),
                         np.allclose(white_marijuana_ratio, 9.4, atol=10e-2),
                         np.allclose(asian_marijuana_ratio, 9.4, atol=10e-2)]
        return [aian_marijuana_ratio, black_marijuana_ratio,
                white_marijuana_ratio, asian_marijuana_ratio], soft_findings, hard_findings

    def finding_6_3(self):
        """
        As shown in Table 1, males were more likely than females to have initiated marijuana first in comparison to
        those not using drugs (aRRR = 1.69), those initiating cigarettes first (aRRR = 1.79), or
        those initiating alcohol first (aRRR = 1.83)
        """
        raise NonReproducibleFindingException

    def finding_6_4(self):
        """
        Likewise, the likelihood of initiating marijuana first relative to no drug use (aRRR = 1.69) or alcohol first
        (aRRR = 1.06) increased with age, but not relative to initiating cigarettes first.
        """
        raise NonReproducibleFindingException

    def finding_6_5(self):
        """
        Compared to Whites, AI/AN youth were 3.7 times more likely to have initiated marijuana first relative to no drug
        use, and were 5.0 times more likely to have initiated marijuana first relative to alcohol
        """
        raise NonReproducibleFindingException

    def finding_6_6(self):
        """
        Notably, Black youth were the most likely to have initiated marijuana first compared to cigarettes (aRRR = 2.74).
        """
        raise NonReproducibleFindingException

    def finding_6_7(self):
        """
        To a lesser extent, Hispanic, Native Hawaiian/Other Pacific Islander (NHOPI), and multiracial youth also had a
        higher likelihood of initiating marijuana before other substances compared to Whites.
        """
        raise NonReproducibleFindingException

    def finding_6_8(self):
        """
        By contrast, Asian youth were less likely to have initiated marijuana first relative to no drug use (aRRR = 0.30)
        or alcohol first (aRRR = 0.59).
        """
        raise NonReproducibleFindingException

    def finding_6_9(self):
        """
        Thus, White and Asian youth were more likely to have initiated cigarettes or alcohol first before other
        substances compared to other racial/ethnic groups.
        """
        raise NonReproducibleFindingException

    def finding_6_10(self):
        """
        However, there was less variation by race/ethnicity among older age groups. For example, 20–21-yearold Black
        youth had a similar likelihood of initiating marijuana first relative to Whites, but 15–16-year-old Black youth
        had almost twice the likelihood (aRRR = 1.9).
        """
        raise NonReproducibleFindingException

    def finding_6_11(self):
        """
        We found no subgroup interactions by sex (i.e., age x sex or race/ethnicity x sex)
        """
        raise NonReproducibleFindingException

    def finding_6_12(self):
        """
        Generally, those who started with a particular substance were the most like to have prevalent problematic use
        of that substance. For example, those who initiated marijuana before other substances were more likely currently
        smoke marijuana heavily and have CUD. Those who initiated alcohol before other substances were the most likely to
        experience prevalent AUD, and those who initiated cigarettes first were the most likely to experience prevalent ND.
        """
        raise NonReproducibleFindingException

    def finding_6_13(self):
        """
        However, it is worth noting that those who initiated marijuana first were no less likely, statistically, to
        have prevalent ND as compared to those who initiated cigarettes first.
        """
        raise NonReproducibleFindingException

    def finding_6_14(self):
        """
        Finally, youth who initiated cigarettes or other tobacco products before other substances were less likely than
        those starting with alcohol or marijuana to have used other drugs, such as cocaine, heroin, inhalants, and
        non-medical prescription drugs.
        """
        raise NonReproducibleFindingException

    def finding_7_1(self):
        """
        We found that, in 2014, 8% of US youths aged 12–21-years reported that marijuana was the first drug they used;
        this percentage has almost doubled since 2004.
        """
        raise NonReproducibleFindingException


if __name__ == '__main__':
    paper = Fairman19Marijuana()
    for find in paper.FINDINGS:
        print(find.run())
