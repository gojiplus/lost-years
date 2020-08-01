#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Tests for secc_caste_ln.py
"""

import os
import shutil
import unittest
import pandas as pd
from lost_years import lost_years_ssa, lost_years_hld, lost_years_who
from . import capture


class TestInRollsFn(unittest.TestCase):

    def setUp(self):
        self.df = pd.read_csv('lost_years/tests/input.csv')

    def tearDown(self):
        pass

    def test_lost_years_ssa(self):
        odf = lost_years_ssa(self.df)
        self.assertIn('ssa_life_expectancy', odf.columns)
        self.assertTrue(odf.iloc[0].ssa_year == 2004)

    def test_lost_years_hld(self):
        odf = lost_years_hld(self.df)
        self.assertIn('hld_life_expectancy', odf.columns)
        self.assertTrue(odf.iloc[0].hld_year1 == 2003)

    def test_lost_years_who(self):
        odf = lost_years_who(self.df)
        self.assertIn('who_life_expectancy', odf.columns)
        self.assertTrue(odf.iloc[0].who_year == 2003)


if __name__ == '__main__':
    unittest.main()
