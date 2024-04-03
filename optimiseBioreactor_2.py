import sys

import os
import subprocess 

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

import math 
import privateLocs

import biota.steadyfluxes as steady

import torch

from ax.service.managed_loop import optimize

sys.path.insert(0, privateLocs.libpath)
import mstar

# M-Star Path setup				
install_path = os.path.dirname(privateLocs.binpath)				
solver_exe = os.path.join(install_path, "mstar-cfd-mgpu")

#mstar.SetVerbose()
mstar.CheckOutLicense()

m=mstar.Load('template_method2.msb')

def getBioreactorMetrics(inputs):

    loc = 'runDir'
    
    if os.path.isdir(loc):
        os.system('rm -r '+loc)
    
    os.makedirs(loc)

    #m=mstar.Load('template_method1.msb')

    m.Get("Moving Body").Get("Rotation Speed").Value = str(inputs[0])    
    m.Get("Bubbles").Get("Volume Feed Rate Expr").Value = str(inputs[1])
    m.Get("Rushton_1").Get("Diameter").Value = inputs[2]
    m.Get("Rushton_1_1").Get("Diameter").Value = inputs[2]
    m.Get("Rushton_1").Get("Hub Diameter").Value = inputs[2] - 0.2
    m.Get("Rushton_1_1").Get("Hub Diameter").Value = inputs[2] - 0.2
    m.Get("Rushton_1").Get("Blade Width").Value = inputs[3]
    m.Get("Rushton_1_1").Get("Blade Width").Value = inputs[3]
    
    m.Export(loc)
    
    if os.path.isfile("running.msb"):
        os.system('rm running.msb')
    
    m.Save("running.msb")

    compl = subprocess.run(['mpirun', '-np' , '2', solver_exe, '-i', 'input.xml', '-o', \
                            'out', '--gpu-ids', '0,1'], cwd=loc,capture_output=True)

    #compl = subprocess.run([solver_exe, '-i', 'input.xml', '-o','out', '--force','--gpu-auto'], cwd=loc,capture_output=True)


    if compl.returncode == 0:
        #get data
        
        #average kLa across probe locations
        df_p0 = pd.read_csv(loc+'/out/Stats/Probe_ProbeArray__0.txt', delimiter = "\t")
        df_p1 = pd.read_csv(loc+'/out/Stats/Probe_ProbeArray__1.txt', delimiter = "\t")
        df_p2 = pd.read_csv(loc+'/out/Stats/Probe_ProbeArray__2.txt', delimiter = "\t")
        df_p3 = pd.read_csv(loc+'/out/Stats/Probe_ProbeArray__3.txt', delimiter = "\t")
        df_p4 = pd.read_csv(loc+'/out/Stats/Probe_ProbeArray__4.txt', delimiter = "\t")
        df_p5 = pd.read_csv(loc+'/out/Stats/Probe_ProbeArray__5.txt', delimiter = "\t")
        t = df_p0['Time [s]'].values

        avgO2 = (df_p0['O2 [mol/L]'].values+df_p1['O2 [mol/L]'].values+df_p2['O2 [mol/L]'].values+\
            df_p3['O2 [mol/L]'].values+df_p4['O2 [mol/L]'].values+df_p5['O2 [mol/L]'].values)/6
        lnavgO2 = -np.log(1-avgO2/(0.032*0.0094))
        kLa_O2 = np.polyfit(t,lnavgO2,1)[0]

        avgCO2 = (df_p0['CO2 [mol/L]'].values+df_p1['CO2 [mol/L]'].values+df_p2['CO2 [mol/L]'].values+\
             df_p3['CO2 [mol/L]'].values+df_p4['CO2 [mol/L]'].values+df_p5['CO2 [mol/L]'].values)/6
        lnavgCO2 = np.log(4.464e-3/avgCO2)
        kLa_CO2 = np.polyfit(t,lnavgCO2,1)[0]

        #get mixing time
        tauM = t[-1] - 10

        #get max eps
        df_maxeps = pd.read_csv(loc+'/out/Stats/GlobalVariables.txt', delimiter = "\t")
        maxEps = df_maxeps['e_t_avg_max'].values[-1]

        #get mean eps
        df_meaneps = pd.read_csv(loc+'/out/Stats/Fluid.txt', delimiter = "\t")
        meanEps = np.mean(df_meaneps['Mean Eddy Dissipation Rate [W/kg]'].values[-10:])

        return((kLa_O2,kLa_CO2,tauM,maxEps,meanEps))

    else: 
        print("MStar Run Error: ", compl.returncode, compl.stderr, compl.stdout)
        os.system('rm -r '+loc)
        return((0,0,0))
    
def TEACFD(parameterization):
    
    #print(parameterization)
    
    rpm=parameterization['RPM']
    Q=parameterization['Gas Flow Rate']
    d=parameterization['Impeller Diameter']
    w=parameterization['Blade Width']

    cfdResults = getBioreactorMetrics((rpm,Q*60000,d,w))
    # print(cfdResults)
    # print(type(cfdResults[1]))

    


    workingVolume = 20000
    tankDiameter = 2.34
    impellerDiameter = tankDiameter/3
    #rpm = 42.3
    backPressure = 1.3
    superficialVel = Q/(math.pi*(tankDiameter/2)**2)
    moleFracO2 = 0.21
    moleFracCO2 = 0.03
    initVol = 0.8 * workingVolume
    initCells = 4e6
    temp = 310
    powerNumber = 5
    mediumDensity = 1000
    mediumViscosity = 9e-4
    vesselVolDay = 0.0
    perfLactateRate = 5.0
    perfAmmrate = 5.0

    bioreactor = steady.Bioreactor(wv=workingVolume,t=tankDiameter,d=impellerDiameter,n=rpm,p_back=backPressure,\
                                   u_s=superficialVel,mf_O2_gas=moleFracO2,mf_CO2_gas=moleFracCO2,v0=initVol,\
                                    ns=initCells,Temp=temp,Np=powerNumber,rho=mediumDensity,mu=mediumViscosity,\
                                        vvd=vesselVolDay,perfAMM=perfAmmrate,perfLAC=perfLactateRate)

    growthRate = 0.029

    glutamineUptakeRate = 0
    glucoseUptakeRate = 0
    oxygenUptakeRate = 0.48963
    uptakeList = [glutamineUptakeRate, glucoseUptakeRate, oxygenUptakeRate]

    carbonDioxideProdRate = 0.593197
    ammoniaProductionRate = 0.013571
    lactateProductionRate = 0.135707
    prodList = [carbonDioxideProdRate, ammoniaProductionRate, lactateProductionRate]

    massDensity = 1030
    cellRadius = 18e-6
    wetmass = 3000
    dryMassFraction = 0.3


    ammoniaLimit = 5
    lactateLimit = 50
    CO2Limit = 100
    turbLengthLimit = 20e-6
    limitsList = [ammoniaLimit, lactateLimit, CO2Limit, turbLengthLimit]


    cell = steady.Cell(mu=growthRate,uptakes=uptakeList,prod=prodList,rho=massDensity,rad=cellRadius,\
                       wetmass=wetmass,dmf=dryMassFraction,limits=limitsList)

    print(bioreactor.ns*1000*cell.wetmass*1e-12)
    
    if (cfdResults[2]>1/cfdResults[0]) or (cfdResults[2]>1/cfdResults[1]) or (cfdResults[3] > 100):
        result = {'yield':(bioreactor.ns*1000*cell.wetmass*1e-12,None)}
        return (result)

    dummy,a = steady.bioreactorODEs(bioreactor,cell,200,klaInO2=float(cfdResults[0]),klaInCO2=float(cfdResults[1]))

    result = {'yield':(min(a['O2'],a['CO2']),None)}

    return (result)

best_parameters, values, experiment, model = optimize(
    parameters=[
        {
            "name": "RPM", 
            "type": "range", 
            "bounds": [20.0, 120.0],
            "value_type": "float",
        },
        {
            "name": "Gas Flow Rate", 
            "type": "range", 
            "bounds": [3.33e-3, 3.33e-2],
            "value_type": "float",
        },
        {
            "name": "Impeller Diameter", 
            "type": "range", 
            "bounds": [0.7, 1.2],
            "value_type": "float",
        },
        {
            "name": "Blade Width", 
            "type": "range", 
            "bounds": [0.1, 0.3],
            "value_type": "float",
        },
    ],
    experiment_name="test",
    evaluation_function=TEACFD,
    #outcome_constraints=["CO2 >= -10.0","Mixing >= -10.0"],  
    objective_name="yield",
    total_trials=30,
)