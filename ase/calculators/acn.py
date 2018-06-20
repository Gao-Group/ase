"""Acetonitrile potential.
   Guardia et al., Molecular Simulation, 2001.
"""

from __future__ import division
import numpy as np
import ase.units as units
from ase.calculators.calculator import Calculator, all_changes
from ase.data import atomic_masses

# Electrostatic constant: 
k_c = units.Hartree * units.Bohr

# Force field parameters
qMe = 0.206
qC = 0.247
qN = -0.453
sigmaMe = 3.775
sigmaC = 3.650
sigmaN = 3.200
sigma=np.array([sigmaMe, sigmaC, sigmaN])
epsilonMe = 0.7824 * units.kJ / units.mol
epsilonC = 0.544 * units.kJ / units.mol
epsilonN = 0.6276 * units.kJ / units.mol
epsilon=np.array([epsilonMe, epsilonC, epsilonN])
rMeC = 1.458
rCN = 1.157
rMeN = rMeC+rCN

# Variables needed to distribute the forces on C to Me and N
CMe=rCN/rMeN
CN=rMeC/rMeN
mMe=atomic_masses[6]+3*atomic_masses[1]
mC=atomic_masses[6]
mN=atomic_masses[7]
MCN=mC*mN
MMeC=mC*mMe
MMeN=mN*mMe
NMe=CMe/(CMe**2*MCN+CN**2*MMeC+MMeN)
NN=CN/(CMe**2*MCN+CN**2*MMeC+MMeN)

def set_acn_charges(atoms, qmidx=0):
    charges = np.empty(len(atoms))
    # Correct atom sequence is:
    # MeCNMeCN ... MeCN or NCMeNCMe ... NCMe
    if atoms.numbers[qmidx] == 7:
       n = qmidx
       me = qmidx+2
    else:
       n = qmidx+2
       me = qmidx
    assert (atoms.numbers[n::3] == 7).all, \
           'Not the correct atoms sequence'
    assert (atoms.numbers[qmidx+1::3] == 6).all, \
           'Not the correct atoms sequence'
    charges[me::3] = qMe
    charges[qmidx+1::3] = qC
    charges[n::3] = qN 
    atoms.set_initial_charges(charges)

def wrap(D, cell, pbc):
    """Wrap distances to nearest neighbor (minimum image convention)."""
    shift = np.zeros_like(D)
    for i, periodic in enumerate(pbc):
        if periodic:
            d = D[:, i]
            L = cell[i]
            shift[:, i] = (d + L / 2) % L - L / 2 - d
    return shift 

def CombineLJ_lorenz_berthelot(sigma, epsilon): 
    """Combine LJ parameters according to the 
       Lorenz-Berthelot rule"""
    sigma_c=np.zeros((len(sigma), len(sigma)))
    epsilon_c=np.zeros_like(sigma_c)

    for ii in range(len(sigma)):
        sigma_c[:, ii]=(sigma[ii]+sigma)/2
        epsilon_c[:, ii]=(epsilon[ii]*epsilon)**0.5
    return sigma_c, epsilon_c         

class ACN(Calculator):
    implemented_properties = ['energy', 'forces']
    nolabel = True
    pcpot = None

    def __init__(self, rc=5.0, width=1.0):
        """ACN potential.

        rc: float
            Cutoff radius for Coulomb part.
        width: float
            Width for cutoff function for Coulomb part.
        """
        self.rc = rc
        self.width = width
        self.forces = None
        Calculator.__init__(self)

    def calculate(self, atoms=None,
                  properties=['energy'],
                  system_changes=all_changes):
        Calculator.calculate(self, atoms, properties, system_changes)

        R = self.atoms.positions.reshape((-1, 3, 3))
        Z = self.atoms.numbers
        pbc = self.atoms.pbc
        cell = self.atoms.cell.diagonal()
        nm = len(R)
        self.nm = nm
        # mc = self.get_molcoms(nm)

        assert (self.atoms.cell == np.diag(cell)).all(), 'not orthorhombic'
        #assert ((cell >= 2 * self.rc) | ~pbc).all(), 'cutoff too large'  # ???
        if Z[0] == 7:
            n = 0
            me = 2
        else:
            n = 2
            me = 0
        assert (Z[n::3] == 7).all(), \
               'Not the correct atoms sequence'                
        assert (Z[1::3] == 6).all, \
               'Not the correct atoms sequence'
        self.n = n
        self.me = me      

        charges = self.atoms[:3].get_initial_charges()

        energy = 0.0
        self.forces = np.zeros((3 * nm, 3))

        for m in range(nm - 1):
            ## Get distances between COM molecule m and m+1:nm
            # Dmm = mc[m + 1:] - mc[m]
            Dmm = R[m + 1:, 1] - R[m, 1]
            # MIC PBCs
            shift = wrap(Dmm, cell, pbc)
        
            # Smooth cutoff
            Dmm += shift
            d2 = (Dmm**2).sum(1)
            d = d2**0.5
            cut, dcut = self.cutoff(d)

            # LJ parameters
            sigma_c, epsilon_c = CombineLJ_lorenz_berthelot(sigma, epsilon) 

            for j in range(3):
                D = R[m + 1:] - R[m, j] + shift[:, np.newaxis]
                r2 = (D**2).sum(axis=2)
                r = r2**0.5
                # Coulomb interactions
                e = charges[j] * charges / r * k_c
                energy += np.dot(cut, e).sum()
                F = (e / r2 * cut[:, np.newaxis])[:, :, np.newaxis] * D 
                Fmm = -(e.sum(1) * dcut / d)[:, np.newaxis] * Dmm       
                self.forces[(m + 1) * 3:] += F.reshape((-1, 3))
                self.forces[m * 3 + j] -= F.sum(axis=0).sum(axis=0)
                self.forces[(m + 1) * 3 + 1::3] += Fmm
                self.forces[m * 3 + 1] -= Fmm.sum(0)
                # LJ interactions 
                c6 = (sigma_c[:, j]**2 / r2)**3
                c12 = c6**2
                e = 4 * epsilon_c[:, j] * (c12 - c6) 
                energy += np.dot(cut, e).sum()                
                F = (24 * epsilon_c[:, j] * (2 * c12 - c6) / r2 * cut[:, np.newaxis])[:, :, np.newaxis] * D
                Fmm = -(e.sum(1) * dcut / d)[:, np.newaxis] * Dmm
                self.forces[(m + 1) * 3:] += F.reshape((-1, 3))
                self.forces[m * 3 + j] -= F.sum(axis=0).sum(axis=0)
                self.forces[(m + 1) * 3 + 1::3] += Fmm
                self.forces[m * 3 + 1] -= Fmm.sum(0)
                
        if self.pcpot:
            e, f = self.pcpot.calculate(np.tile(charges, nm),
                                        self.atoms.positions)
            energy += e
            self.forces += f
        
        f_new = self.redistribute_forces(self.n, self.me, self.forces)
        self.forces = f_new

        self.results['energy'] = energy
        self.results['forces'] = self.forces
 
    def redistribute_forces(self, n, me, f_old):
        """Ciccotti et al., Molecular Physics, 1982.
        """        
        f_new = np.zeros_like(f_old)
        
        # N
        f_new[n::3, :] = (1-NN*MMeC*CN)*f_old[n::3, :]-NN*MCN*CMe*f_old[me::3, :]+NN*MMeN*f_old[1::3, :]
        # Me 
        f_new[me::3, :] = (1-NMe*MCN*CMe)*f_old[me::3, :]-NMe*MMeC*CN*f_old[n::3, :]+NMe*MMeN*f_old[1::3, :]
 
        return f_new                 

    def get_molcoms(self, nm):      
        molcoms = np.zeros((nm, 3))      
        for m in range(nm): 
            molcoms[m] = self.atoms[m*3:(m+1)*3].get_center_of_mass() 
        return molcoms
 
    def cutoff(self, d): 
        x1 = d > self.rc - self.width  
        x2 = d < self.rc 
        x12 = np.logical_and(x1, x2)    
        y = (d[x12] - self.rc + self.width) / self.width  
        cut = np.zeros(len(d))  # cutoff function    
        cut[x2] = 1.0     
        cut[x12] -= y**2 * (3.0 - 2.0 * y)    
        dtdd = np.zeros(len(d))     
        dtdd[x12] -= 6.0 / self.width * y * (1.0 - y)        
        return cut, dtdd

    def embed(self, charges):
        """Embed atoms in point-charges."""
        self.pcpot = PointChargePotential(charges)
        return self.pcpot

    def check_state(self, atoms, tol=1e-15):
        system_changes = Calculator.check_state(self, atoms, tol)
        if self.pcpot and self.pcpot.mmpositions is not None:
            system_changes.append('positions')
        return system_changes

class PointChargePotential:
    def __init__(self, mmcharges):
        """Point-charge potential for ACN.

        Only used for testing QMMM.
        """
        self.mmcharges = mmcharges
        self.mmpositions = None
        self.mmforces = None

    def set_positions(self, mmpositions):
        self.mmpositions = mmpositions

    def calculate(self, qmcharges, qmpositions):
        energy = 0.0
        self.mmforces = np.zeros_like(self.mmpositions)
        qmforces = np.zeros_like(qmpositions)
        for C, R, F in zip(self.mmcharges, self.mmpositions, self.mmforces):
            d = qmpositions - R
            r2 = (d**2).sum(1)
            e = units.Hartree * units.Bohr * C * r2**-0.5 * qmcharges
            energy += e.sum()
            f = (e / r2)[:, np.newaxis] * d
            qmforces += f
            F -= f.sum(0)
        self.mmpositions = None
        return energy, qmforces

    def get_forces(self, calc):
        return self.mmforces

