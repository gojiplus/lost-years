# Lost Years: Expected Number of Years Lost

[![PyPI Version](https://img.shields.io/pypi/v/lost-years.svg)](https://pypi.python.org/pypi/lost-years)
[![Documentation Status](https://github.com/gojiplus/lost_years/actions/workflows/docs.yml/badge.svg)](https://gojiplus.github.io/lost_years/)
[![Downloads](https://static.pepy.tech/badge/lost-years)](https://pepy.tech/project/lost-years)

Mortality rate is puzzling to mortals. A better number is the expected number of years lost. (A yet better number would be quality-adjusted years lost.) To make it easier to calculate the expected years lost, `lost_years` provides a convenient way to join to the [SSA actuarial data](https://www.ssa.gov/oact/HistEst/PerLifeTables/), [HLD data](https://www.lifetable.de/), and [WHO life table data](https://platform.who.int/mortality).

**Data Currency Note**: The packaged data covers years up to 2016. For the most recent data (2023-2024), use the data update script: `python scripts/update_data.py`

The package exposes three functions: `lost_years_ssa`, `lost_years_hld`, and `lost_years_who`:

* **`lost_years_ssa`**: Joins to the final SSA dataset stored [here](https://github.com/gojiplus/lost_years/blob/master/lost_years/data/ssa/ssa.csv). The data are from [SSA actuarial data](https://www.ssa.gov/oact/STATS/)

    * **Inputs:**
        * The function expects 4 inputs: `age, sex, and year`. If any of the inputs are not available, it errors out.
        * **Closest Year and Age Matching** By default, we match to the closest year; The year we match to is stored as `ssa_year.` Same for age. If the age provided is not available, we match to the closest age and store the matched age in the `ssa_age` column.

    * **What the function does**
        * While `lost_years_ssa` is technically only applicable for the US, we make it so that the function ignores the `country` argument and gives you the counterfactual of what the expected years lost would be if the person who died (or is predicted to die) was in the US. (You can of course do the same for HLD by changing the country.)

* **`lost_years_hld`**: Joins to the international [life table](https://www.lifetable.de/) data.

    * **Inputs:**
        * The function expects 4 inputs: `age, sex, year, and country`. If any of the inputs are not available, it errors out.
        * **Closest Year and Age Matching** By default, we match to the closest year; not all countries provide expected years left for all years or all ages. The year we match to is `hld_year1`. Same for age. If the age provided is not available, we match to the closest age and store the matched age in the `hld_age` column.

    * **What the function does**
        * HLD exposes more facets than age and sex. For some countries, for some periods, it also provides things like sociodemographic variables. To not lose information, we provide **multiple rows—corresponding to each sub-combination—per match**.

    * **Output**
        * The original codebook for HLD is posted [here](https://github.com/gojiplus/lost_years/blob/master/lost_years/data/hld/formats.pdf). For more information, check [HLD](https://www.lifetable.de/).
        * To make it easier to use, we normalize the column names.

* **`lost_years_who`**: Joins to the international [life table](https://platform.who.int/mortality) data.

    * **Inputs:**
        * The function expects 4 inputs: `age, sex, year, and country`. If any of the inputs are not available, it errors out.
        * **Closest Year and Age Matching** By default, we match to the closest year; not all countries provide expected years left for all years or all ages. The year we match to is `who_year`. Same for age. If the age provided is not available, we match to the closest age and store the matched age in the `who_age` column.

    * **What the function does**
        * Joins to WHO data

    * **Output**
        * To make it easier to use, we normalize the column names.

## Application

We illustrate the use of the package by estimating the average number of years by which people's lives are shortened due to coronavirus.

**China:** Using data from [Table 1 of the paper](http://weekly.chinacdc.cn/en/article/id/e53946e2-c6c4-41e9-9a9b-fea8db1a8f51) that gives us the distribution of ages of people who died from COVID-19 in China, with conservative assumptions (assuming the gender of the dead person to be male, taking the middle of age ranges) [we find](https://github.com/gojiplus/lost_years/blob/master/docs/source/examples/corona_virus.ipynb) that people's lives are shortened by about 11 years on average. These estimates are conservative for one additional reason: there is likely an inverse correlation between people who die and their expected longevity. And note that given a bulk of the deaths are among older people, when people are more infirm, the quality-adjusted years lost is likely yet more modest. Given that the last life tables from China are from 1981 and given life expectancy in China has risen substantially since then (though most gains come from reductions in childhood mortality, etc.), we exploit the recent data from the US, simulating what the losses would be if people had the same aggregate life tables as Americans. Using the most recent SSA data, we find that the number to be 16. Compare this to deaths from road accidents, the modal reason for death among 5-24, and 25-44 ages in the US. Assuming everyone who dies from a traffic accident is a man, and assuming the age of death to be 25, we get ~52 years, roughly 3x as large as coronavirus.

**France:** Using [COVID-19 Electronic Death Certification Data (CEPIDC)](https://www.data.gouv.fr/fr/datasets/donnees-de-certification-electronique-des-deces-associes-au-covid-19-cepidc/), like above, we estimate the average number of years lost by people dying of coronavirus. With conservative assumptions (assuming gender of the dead person to be male, taking the middle of age ranges) [we find](https://github.com/gojiplus/lost_years/blob/master/docs/source/examples/corona_virus_fr.ipynb) that people's lives are shortened by about 9 years on average. Surprisingly, the average number of years lost of the people dying of coronavirus [remained steady](https://github.com/gojiplus/lost_years/blob/master/docs/source/examples/corona_virus_fr_daily.ipynb) at about 9 years between March and July 2020.

## Installation

We strongly recommend installing `lost_years` inside a Python virtual environment (see [venv documentation](https://docs.python.org/3/library/venv.html#creating-virtual-environments))

```bash
pip install lost-years
```

## Using lost_years

### Command Line Interface

The package provides three command-line tools:

```bash
# US data (SSA)
lost_years_ssa input.csv -o output.csv

# International data (HLD) 
lost_years_hld input.csv -o output.csv

# Global data (WHO)
lost_years_who input.csv -o output.csv
```

All commands expect a CSV file with columns for age, sex, year (and country for HLD/WHO). See the [full CLI documentation](https://gojiplus.github.io/lost-years/cli.html) for all options and examples.

### As an External Library

Please also look at the Jupyter notebook [example.ipynb](https://github.com/gojiplus/lost_years/blob/master/docs/source/examples/example.ipynb).

### As an External Library with Pandas DataFrame

```python
>>> import pandas as pd
>>> from lost_years import lost_years_ssa, lost_years_hld, lost_years_who
>>>
>>> df = pd.read_csv('lost_years/tests/input.csv')
>>> df
   year country  age sex
0  2003     BRA   80   M
1  2019     BLZ    5   M
2  1999     PHL   62   F
3  2001     THA    7   F
4  2006     CHE   57   F
5  2014     MNE   44   M
6  2004     SLV   34   F
7  2003     MKD   46   M
8  2014     MKD    6   F
9  1997     LBN   49   F
>>>
>>> lost_years_ssa(df)
   year country  age sex  ssa_age  ssa_year  ssa_life_expectancy
0  2003     BRA   80   M       80      2004                 7.62
1  2019     BLZ    5   M        5      2016                71.60
2  1999     PHL   62   F       62      2004                21.89
3  2001     THA    7   F        7      2004                73.56
4  2006     CHE   57   F       57      2006                26.33
5  2014     MNE   44   M       44      2014                34.95
6  2004     SLV   34   F       34      2004                47.18
7  2003     MKD   46   M       46      2004                31.90
8  2014     MKD    6   F        6      2014                75.62
9  1997     LBN   49   F       49      2004                33.15
>>>
>>> lost_years_hld(df)
   year country  age sex hld_country  ... hld_sex hld_age hld_age_interval hld_life_expectancy  hld_life_expectancy_orig
0  2003     BRA   80   M         BRA  ...       1      80               99                5.18                      8.78
0  2003     BRA   80   M         BRA  ...       1      80               99                5.18                      8.78
1  2019     BLZ    5   M         BLZ  ...       1       5                5               65.79                     67.61
2  1999     PHL   62   F         PHL  ...       2      60                5               20.07                     20.11
2  1999     PHL   62   F         PHL  ...       2      60                5               19.57                      19.6
3  2001     THA    7   F         THA  ...       2       5                5               71.56                        73
4  2006     CHE   57   F         CHE  ...       2      57                1               28.66                      28.7
5  2014     MNE   44   M         MNE  ...       1      44                1               29.31                     29.31
6  2004     SLV   34   F         SLV  ...       2      35                5               41.90                      41.9
7  2003     MKD   46   M         MKD  ...       1      46                1               28.36                     28.36
8  2014     MKD    6   F         MKD  ...       2       6                1               72.26                     72.25
9  1997     LBN   49   F         LBN  ...       2      50                5               27.48                      27.7

[12 rows x 19 columns]
>>>
>>> lost_years_who(df)
year country  age sex  who_age who_country  who_life_expectancy who_sex  who_year
0  2003     BRA   80   M       80         BRA                  5.7     MLE      2003
1  2019     BLZ    5   M        5         BLZ                 64.0     MLE      2016
2  1999     PHL   62   F       60         PHL                 18.2    FMLE      2000
3  2001     THA    7   F        5         THA                 71.2    FMLE      2001
4  2006     CHE   57   F       55         CHE                 30.6    FMLE      2006
5  2014     MNE   44   M       45         MNE                 30.8     MLE      2014
6  2004     SLV   34   F       35         SLV                 42.8    FMLE      2004
7  2003     MKD   46   M       45         MKD                 28.9     MLE      2003
8  2014     MKD    6   F        5         MKD                 73.4    FMLE      2014
9  1997     LBN   49   F       50         LBN                 28.6    FMLE      2000
```

## Documentation

For more information, please see [project documentation](https://gojiplus.github.io/lost-years/).

## Authors

Suriyan Laohaprapanon and Gaurav Sood

## Contributor Code of Conduct

The project welcomes contributions from everyone! In fact, it depends on it. To maintain this welcoming atmosphere, and to collaborate in a fun and productive way, we expect contributors to the project to abide by the [Contributor Code of Conduct](https://www.contributor-covenant.org/version/2/0/code_of_conduct/).

## License

The package is released under the [MIT License](https://opensource.org/licenses/MIT).
