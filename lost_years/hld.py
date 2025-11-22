#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys
import argparse
import pandas as pd

try:
    from importlib.resources import files
except ImportError:
    from importlib_resources import files

from .utils import column_exists, fixup_columns, closest, download_file

HLD_URL = 'https://www.lifetable.de/data/hld.zip'
HLD_DATA = str(files("lost_years") / "data" / "hld.zip")
HLD_TRANS = str(files("lost_years") / "data" / "hld_translation.csv")
HLD_COLS = ['Country', 'Region', 'Residence', 'Ethnicity', 'SocDem',
            'Version', 'Ref-ID', 'Year1', 'Year2', 'TypeLT', 'Sex',
            'Age', 'AgeInt', 'e(x)', 'e(x)Orig']
HLD_COLS_REMAP = {'year1': 'year'}


class LostYearsHLDData():
    __df = None
    __hld_trans = {}

    @classmethod
    def lost_years_hld(cls, df, cols=None, download_latest=False):
        """Appends Life expectancy column from HLD data to the input DataFrame
        based on country, age, sex and year in the specific cols mapping

        Args:
            df (:obj:`DataFrame`): Pandas DataFrame containing the last name
                column.
            cols (dict or None): Column mapping for country, age, sex, and year
                in DataFrame
                (None for default mapping: {'country': 'country', 'age': 'age',
                                            'sex': 'sex', 'year': 'year'})
        Returns:
            DataFrame: Pandas DataFrame with HLD data columns:-
                'hld_country', 'hld_age', 'hld_sex', 'hld_year1', ...
        """
        df_cols = {}
        for col in ['country', 'age', 'sex', 'year']:
            tcol = col if cols is None else cols[col]
            if tcol not in df.columns:
                print("No column `{0!s}` in the DataFrame".format(tcol))
                return df
            df_cols[col] = tcol

        if cls.__df is None:
            if download_latest or not os.path.exists(HLD_DATA):
                print('Download latest HLD data from lifetable.de...'
                      '(may take a few minutes)...')
                download_file(HLD_URL, HLD_DATA)
            cls.__df = pd.read_csv(HLD_DATA, usecols=HLD_COLS,
                                   low_memory=False)
            cls.__hld_trans = {}
            with open(HLD_TRANS) as f:
                for l in f:
                    a = l.strip().split(',')
                    if len(a) == 2:
                        cls.__hld_trans[a[0]] = a[1]
            cls.__df.rename(columns=cls.__hld_trans, inplace=True)                        
            cls.__df.rename(columns=HLD_COLS_REMAP, inplace=True)
            cls.__df.drop_duplicates(inplace=True)

        # back up and create temp sex column
        df.rename(columns={df_cols['sex']: '__sex'}, inplace=True)
        df['sex'] = df['__sex'].apply(lambda c: 1 if c.lower() in ['m', 'male'] else 2)

        out_df = pd.DataFrame()
        for i, r in df.iterrows():
            sdf = cls.__df
            for c in ['country', 'age', 'sex', 'year']:
                if sdf[c].dtype in ['int64', 'float64']:
                    sdf = sdf[sdf[c] == closest(sdf[c].unique(), r[df_cols[c]])]
                else:
                    sdf = sdf[sdf[c].str.lower()==r[df_cols[c]].lower()]
            ageint = cls.__hld_trans['AgeInt']
            sdf = sdf[sdf[ageint]==sdf[ageint].min()]
            ver = cls.__hld_trans['Version']
            sdf = sdf[sdf[ver]==sdf[ver].max()]
            odf = sdf.copy()
            odf['index'] = i
            out_df = pd.concat([out_df, odf])
        out_df.set_index('index', drop=True, inplace=True)
        remap = dict([(value, key) for key, value in HLD_COLS_REMAP.items()]) 
        out_df.rename(columns=remap, inplace=True)
        out_df.columns = ['hld_' + c for c in out_df.columns]
        # take out temp and restore back sex column
        del df['sex']
        df.rename(columns={'__sex': df_cols['sex']}, inplace=True)
        rdf = df.join(out_df)

        return rdf


lost_years_hld = LostYearsHLDData.lost_years_hld


def main(argv=sys.argv[1:]):
    title = ('Appends Lost Years data column(s) by country, age, sex and year')
    parser = argparse.ArgumentParser(description=title)
    parser.add_argument('input', default=None,
                        help='Input file')
    parser.add_argument('-c', '--country', default='country',
                        help='Columns name of country in the input file'
                             '(default=`country`)')
    parser.add_argument('-a', '--age', default='age',
                        help='Columns name of age in the input file'
                             '(default=`age`)')
    parser.add_argument('-s', '--sex', default='sex',
                        help='Columns name of sex in the input file'
                             '(default=`sex`)')
    parser.add_argument('-y', '--year', default='year',
                        help='Columns name of year in the input file'
                             '(default=`year`)')
    parser.add_argument('-o', '--output', default='lost-years-output.csv',
                        help='Output file with Lost Years data column(s)')
    parser.add_argument('--download-hld', action='store_true',
                        help='Download latest HLD from lifetable.de')

    args = parser.parse_args(argv)

    print(args)

    df = pd.read_csv(args.input)

    if not column_exists(df, args.country):
        print("Column: `{0!s}` not found in the input file".format(args.country))
        return -1

    if not column_exists(df, args.age):
        print("Column: `{0!s}` not found in the input file".format(args.age))
        return -1

    if not column_exists(df, args.sex):
        print("Column: `{0!s}` not found in the input file".format(args.sex))
        return -1

    if not column_exists(df, args.year):
        print("Column: `{0!s}` not found in the input file".format(args.year))
        return -1

    rdf = lost_years_hld(df, cols={'country': args.country, 'age': args.age,
                                   'sex': args.sex, 'year': args.year},
                         download_latest=args.download_hld)

    print("Saving output to file: `{0:s}`".format(args.output))
    rdf.columns = fixup_columns(rdf.columns)
    rdf.to_csv(args.output, index=False)

    return 0


if __name__ == "__main__":
    sys.exit(main())
