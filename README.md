# Lost Years: Expected Number of Years Lost

[![PyPI Version](https://img.shields.io/pypi/v/lost-years.svg)](https://pypi.python.org/pypi/lost-years)
[![Documentation Status](https://github.com/gojiplus/lost-years/actions/workflows/docs.yml/badge.svg)](https://gojiplus.github.io/lost-years/)
[![Downloads](https://static.pepy.tech/badge/lost-years)](https://pepy.tech/project/lost-years)

Mortality rate is puzzling to mortals. A better number is the expected number of years lost. (A yet better number would be quality-adjusted years lost.) To make it easier to calculate the expected years lost, `lost_years` provides a convenient way to join to the [SSA actuarial data](https://www.ssa.gov/oact/HistEst/PerLifeTables/), [HLD data](https://www.lifetable.de/), and [WHO life table data](https://platform.who.int/mortality).

**Data Currency Note**: the packaged SSA table is the 2022 period life table, WHO covers 2000-2021, and HLD is the 07.04.2025 release covering 1751-2023. To refresh them, run the per-source maintenance scripts under `lost_years/data/`; HLD still needs a manual download from [lifetable.de](https://www.lifetable.de/).

**Every lookup either answers the question asked or says it cannot.** Each function returns a `*_match_status` column, and a row that could not be matched carries a missing life expectancy rather than the nearest number that happened to be in the table. The matching rules for each source are summarised below.

The package exposes three functions: `lost_years_ssa`, `lost_years_hld`, and `lost_years_who`:

* **`lost_years_ssa`**: Joins to the final SSA dataset stored [here](https://github.com/gojiplus/lost_years/blob/master/lost_years/data/ssa/ssa.csv). The data are from [SSA actuarial data](https://www.ssa.gov/oact/STATS/)

    * **Inputs:** `age`, `sex`, `year`.
    * **Matching:** the matched age and year are reported in `ssa_age` and `ssa_year`. The package ships one SSA table (2022), so a year more than `year_tolerance` (default 5) away returns nothing; pass `year_tolerance=None` to accept any distance.
    * **What the function does:** `lost_years_ssa` is only applicable to the US, so it ignores country and gives the counterfactual of what the expected years lost would be if the person who died had US mortality.

* **`lost_years_hld`**: Joins to the international [life table](https://www.lifetable.de/) data.

    * **Inputs:** `age`, `sex`, `year`, `country` (ISO-3166-1 alpha-3, matched exactly and case-insensitively).
    * **Matching:** HLD is a collection of *published* life tables, so one country-year is often covered by several. The default returns the **single whole-country, total-population table** chosen by the documented rule in the data dictionary (`docs/source/data-dictionary.md`): drop HLD's redundant re-abridgements, quarantine tables whose recalculated and published life expectancies disagree, keep the tables whose period contains the requested year, prefer the narrowest period, and break what is left by a fixed convention. `hld_n_candidates` reports how many tables that last step chose between.
    * **Sub-populations:** HLD also carries regions, urban/rural splits, ethnic groups and socio-demographic groups. Pass `subpopulations=True` to get **one row per sub-population** instead of the national total; the output then has more rows than the input.
    * **Age intervals:** many HLD tables are abridged, so "age 20" may come from an interval covering 20-24. The matched interval is reported in `hld_age` and `hld_age_interval` (99 marks the open-ended top interval).

    * **Output**
        * The original codebook for HLD is posted [here](https://github.com/gojiplus/lost_years/blob/master/lost_years/data/hld/formats.pdf). For more information, check [HLD](https://www.lifetable.de/).
        * To make it easier to use, we normalize the column names.

* **`lost_years_who`**: Joins to the WHO [life expectancy at birth](https://platform.who.int/mortality) indicator.

    * **Inputs:** `sex`, `year`, `country`. **There is no age input**: the packaged WHO table is indicator WHOSIS_000001, life expectancy *at birth*, and has no age dimension. The returned column is named `who_life_expectancy_at_birth` to say so, and passing an `age` mapping raises `ValueError` rather than being ignored. For remaining life expectancy at a given age, use `lost_years_hld`.
    * **Matching:** the matched year is reported in `who_year`; the table covers 2000-2021 and a year more than `year_tolerance` (default 5) away returns nothing.

### Matching rules

| | SSA | HLD | WHO |
|---|---|---|---|
| country | ignored (US only) | exact ISO-3, case-insensitive | exact ISO-3, case-insensitive |
| year | nearest, within 5 years | period must contain the year | nearest, within 5 years |
| age | nearest, within 1 year | the interval containing the age | not applicable |
| missing input | returns nothing, with a reason | returns nothing, with a reason | returns nothing, with a reason |
| rows out | one per input row | one per input row (more with `subpopulations=True`) | one per input row |

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

All commands expect a CSV file with columns for age, sex and year (and country for HLD/WHO; `lost_years_who` takes no age column). `lost_years_hld` also accepts `--subpopulations`, `--year-tolerance` and `--no-quarantine`. See the [full CLI documentation](https://gojiplus.github.io/lost-years/cli.html) for all options and examples.

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
>>> lost_years_ssa(df)[['year', 'age', 'sex', 'ssa_age', 'ssa_year', 'ssa_life_expectancy']]
   year  age sex  ssa_age  ssa_year  ssa_life_expectancy
0  2003   80   M      NaN       NaN                  NaN
1  2019    5   M      5.0    2022.0                70.29
2  1999   62   F      NaN       NaN                  NaN
3  2001    7   F      NaN       NaN                  NaN
4  2006   57   F      NaN       NaN                  NaN
5  2014   44   M      NaN       NaN                  NaN
6  2004   34   F      NaN       NaN                  NaN
7  2003   46   M      NaN       NaN                  NaN
8  2014    6   F      NaN       NaN                  NaN
9  1997   49   F      NaN       NaN                  NaN
```

Only 2019 is within five years of the one packaged SSA table; the rest say
`closest available value 2022 is more than 5.0 from 2003` in `ssa_match_status`
instead of quietly reporting the 2022 figure.

HLD matches on the period a life table actually covers, so a country-year no
table covers returns nothing. `year_tolerance` reaches to the nearest period
and records how far it reached:

```python
>>> cols = ['country', 'year', 'age', 'hld_life_expectancy', 'hld_year1',
...         'hld_year2', 'hld_age', 'hld_age_interval', 'hld_n_candidates',
...         'hld_match_status']
>>> lost_years_hld(df, year_tolerance=5)[cols]
  country  year  age  hld_life_expectancy  hld_year1  hld_year2  hld_age  hld_age_interval  hld_n_candidates                      hld_match_status
0     BRA  2003   80                 5.18     2001.0     2001.0     80.0              99.0               1.0    ok: nearest period, 2 year(s) away
1     BLZ  2019    5                  NaN        NaN        NaN      NaN               NaN               NaN  no eligible life table covering year
2     PHL  1999   62                20.07     2000.0     2000.0     60.0               5.0               1.0    ok: nearest period, 1 year(s) away
3     THA  2001    7                  NaN        NaN        NaN      NaN               NaN               NaN    no eligible life table for country
4     CHE  2006   57                28.92     2007.0     2007.0     57.0               1.0               2.0    ok: nearest period, 1 year(s) away
5     MNE  2014   44                  NaN        NaN        NaN      NaN               NaN               NaN  no eligible life table covering year
6     SLV  2004   34                46.54     2000.0     2000.0     30.0               5.0               1.0    ok: nearest period, 4 year(s) away
7     MKD  2003   46                28.36     2006.0     2008.0     46.0               1.0               1.0    ok: nearest period, 3 year(s) away
8     MKD  2014    6                72.26     2014.0     2016.0      6.0               1.0               3.0                                    ok
9     LBN  1997   49                31.99     1998.0     1998.0     45.0               5.0               1.0    ok: nearest period, 1 year(s) away
```

Thailand has no whole-country table in HLD at all -- only sub-national ones --
so it gets no estimate rather than a silently substituted sub-population
figure. Row 8 is the only exact match: the 2014-2016 Macedonian table covers
2014, three tables were eligible, and the tie-break convention picked one.

```python
>>> lost_years_who(df)[['country', 'year', 'sex', 'who_year',
...                     'who_life_expectancy_at_birth']]
  country  year sex  who_year  who_life_expectancy_at_birth
0     BRA  2003   M      2003                     68.878514
1     BLZ  2019   M      2019                     72.549151
2     PHL  1999   F      2000                     73.996939
3     THA  2001   F      2001                     75.472367
4     CHE  2006   F      2006                     83.621429
5     MNE  2014   M      2014                     74.057255
6     SLV  2004   F      2004                     77.488542
7     MKD  2003   M      2003                     70.946491
8     MKD  2014   F      2014                     77.304988
9     LBN  1997   F      2000                     77.000376
```

These are life expectancies **at birth**, not remaining years at the age in
each row -- the WHO table has no age dimension.

## Documentation

For more information, please see [project documentation](https://gojiplus.github.io/lost-years/).

## Authors

Suriyan Laohaprapanon and Gaurav Sood

## Contributor Code of Conduct

The project welcomes contributions from everyone! In fact, it depends on it. To maintain this welcoming atmosphere, and to collaborate in a fun and productive way, we expect contributors to the project to abide by the [Contributor Code of Conduct](https://www.contributor-covenant.org/version/2/0/code_of_conduct/).

## License

The package is released under the [MIT License](https://opensource.org/licenses/MIT).
