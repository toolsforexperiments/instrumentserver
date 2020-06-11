# -*- coding: utf-8 -*-
"""
Created on Wed Jun 10 13:47:56 2020

@author: Ryan
"""


from wolframclient.evaluation import WolframLanguageSession
from wolframclient.language import wl
session = WolframLanguageSession()

sample = session.evaluate(wl.RandomVariate(wl.NormalDistribution(0,1),1e6))

