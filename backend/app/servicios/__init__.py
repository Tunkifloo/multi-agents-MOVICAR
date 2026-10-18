"""Capa determinista: equivale a los subflujos sw_* de la arquitectura v3.

Es la ÚNICA capa que escribe en la base de datos. Los agentes llaman a estas funciones
mediante herramientas (app/agentes/herramientas.py) y nunca usan SQL ni la BD directamente.
"""
