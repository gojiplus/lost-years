#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys
import argparse
import re
import pandas as pd

from pkg_resources import resource_filename

from .utils import column_exists, fixup_columns, closest

WHO_DATA = resource_filename(__name__, "data/who-lt.csv.gz")
WHO_TRANS = resource_filename(__name__, "data/who_translation.csv")
WHO_COLS = ['COUNTRY (CODE)', 'YEAR (CODE)', 'SEX (CODE)',
            'AGEGROUP (CODE)', 'Display Value', 'GHO (CODE)']
WHO_COLS_REMAP = {'year': 'year'}


class LostYearsWHOData():
    __df = None
    __who_trans = {}

    @classmethod
    def lost_years_who(cls, df, cols=None):
        """Appends Life expectancy column from WHO data to the input DataFrame
        based on country, age, sex and year in the specific cols mapping

        Args:
            df (:obj:`DataFrame`): Pandas DataFrame containing the last name
                column.
            cols (dict or None): Column mapping for country, age, sex, and year
                in DataFrame
                (None for default mapping: {'country': 'country', 'age': 'age',
                                            'sex': 'sex', 'year': 'year'})
        Returns:
            DataFrame: Pandas DataFrame with WHO data columns:-
                'who_country', 'who_age', 'who_sex', 'who_year', ...
        """
        df_cols = {}
        for col in ['country', 'age', 'sex', 'year']:
            tcol = col if cols is None else cols[col]
            if tcol not in df.columns:
                print("No column `{0!s}` in the DataFrame".format(tcol))
                return df
            df_cols[col] = tcol

        if cls.__df is None:
            cls.__df = pd.read_csv(WHO_DATA, usecols=WHO_COLS,
                                   low_memory=False)
            cls.__df.drop(cls.__df.loc[cls.__df['GHO (CODE)']!='LIFE_0000000035'].index, inplace=True)
            cls.__df.drop(columns=['GHO (CODE)'], inplace=True)
            cls.__who_trans = {}
            with open(WHO_TRANS) as f:
                for l in f:
                    a = l.strip().split(',')
                    if len(a) == 2:
                        cls.__who_trans[a[0]] = a[1]
            cls.__df.rename(columns=cls.__who_trans, inplace=True)                        
            cls.__df.rename(columns=WHO_COLS_REMAP, inplace=True)
            cls.__df.drop_duplicates(inplace=True)
            cls.__df['age'] = cls.__df['age'].apply(lambda c: cls.convert_agegroup(c))
            cls.__df['year'] = cls.__df['year'].astype(int)

        # back up and create temp sex column
        df.rename(columns={df_cols['sex']: '__sex'}, inplace=True)
        df['sex'] = df['__sex'].apply(lambda c: 'MLE' if c.lower() in ['m', 'male', 'mle'] else 'FMLE')

        out_df = pd.DataFrame()
        for i, r in df.iterrows():
            sdf = cls.__df
            for c in ['country', 'age', 'sex', 'year']:
                if sdf[c].dtype in ['int64', 'float64']:
                    sdf = sdf[sdf[c] == closest(sdf[c].unique(), r[df_cols[c]])]
                else:
                    sdf = sdf[sdf[c].str.lower()==r[df_cols[c]].lower()]
            odf = sdf.copy()
            odf['index'] = i
            out_df = pd.concat([out_df, odf])
        out_df.set_index('index', drop=True, inplace=True)
        remap = dict([(value, key) for key, value in WHO_COLS_REMAP.items()]) 
        out_df.rename(columns=remap, inplace=True)
        out_df.columns = ['who_' + c for c in out_df.columns]
        # take out temp and restore back sex column
        del df['sex']
        df.rename(columns={'__sex': df_cols['sex']}, inplace=True)
        rdf = df.join(out_df)

        return rdf

    @classmethod
    def convert_agegroup(cls, ag):
        if ag == 'AGE100+':
            return 100
        if ag == 'AGE85PLUS':
            return 85
        if ag == 'AGELT1':
            return 1
        m = re.match('AGE(\d+)\-(\d+)', ag)
        if m:
            return int(m.group(1))
        else:
            return 0

lost_years_who = LostYearsWHOData.lost_years_who


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

    rdf = lost_years_who(df, cols={'country': args.country, 'age': args.age,
                                   'sex': args.sex, 'year': args.year})

    print("Saving output to file: `{0:s}`".format(args.output))
    rdf.columns = fixup_columns(rdf.columns)
    rdf.to_csv(args.output, index=False)

    return 0


if __name__ == "__main__":
    sys.exit(main())
