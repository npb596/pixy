import sys
sys.path.append("/home/npb0015/conda/pkgs/scikit-allel-1.3.5-py38h43a58ef_1/lib/python3.8/site-packages/")
sys.path.append("/home/npb0015/conda/pkgs/asciitree-0.3.3-py_2/site-packages/")
sys.path.append("/home/npb0015/conda/pkgs/numcodecs-0.9.1-py38h709712a_2/lib/python3.8/site-packages/")
sys.path.append("/home/npb0015/conda/pkgs/zarr-2.11.0-pyhd8ed1ab_0/site-packages/")
sys.path.append("/home/npb0015/conda/pkgs/fasteners-0.17.3-pyhd8ed1ab_0/site-packages/")
sys.path.append("/home/npb0015/conda/pkgs/multiprocess-0.70.12.2-py38h497a2fe_1/lib/python3.8/site-packages/")
import warnings
import allel
import numpy as np
from time import perf_counter

from scipy import special
from itertools import combinations
from collections import Counter

# vectorized functions for calculating pi and dxy 
# these are reimplementations of the original functions

# helper function for calculation of pi
# for the given site (row of the count table) count # of differences, # of comparisons, and # missing.
# uses number of haploid samples (n_haps) to determine missing data
def count_diff_comp_missing(row, n_haps):
    
    diffs = row[1] * row[0] 
    gts = row[1] + row[0]
    comps = int(special.comb(gts, 2))
    missing = int(special.comb(n_haps, 2)) - comps
    return diffs, comps, missing

# function for vectorized calculation of pi from a pre-filtered scikit-allel genotype matrix
def calc_pi(gt_array):
     
    # counts of each of the two alleles at each site
    allele_counts = gt_array.count_alleles(max_allele = 1)
    
    # the number of (haploid) samples in the population
    n_haps = gt_array.n_samples * gt_array.ploidy
    
    # compute the number of differences, comparisons, and missing data at each site
    diff_comp_missing_matrix = np.apply_along_axis(count_diff_comp_missing, 1, allele_counts, n_haps) 
    
    # sum up the above quantities for totals for the region
    diff_comp_missing_sums = np.sum(diff_comp_missing_matrix, 0)
    
    # extract the component values
    total_diffs = diff_comp_missing_sums[0]
    total_comps = diff_comp_missing_sums[1]
    total_missing = diff_comp_missing_sums[2]
    
    # alternative method for calculating total_missing
    # produces the same result as original method (included as sanity check)
    # total_possible = ((n_haps * (n_haps-1))/2) * len(allele_counts)
    # total_missing = total_possible - total_comps
    
    # if there are valid data (comparisons between genotypes) at the site, compute average dxy
    # otherwise return NA
    if total_comps > 0:
        avg_pi = total_diffs/total_comps
    else:
        avg_pi = "NA"
        
    return(avg_pi, total_diffs, total_comps, total_missing)

# function for vectorized calculation of dxy from a pre-filtered scikit-allel genotype matrix
def calc_dxy(pop1_gt_array, pop2_gt_array):
    
    # the counts of each of the two alleles in each population at each site
    pop1_allele_counts = pop1_gt_array.count_alleles(max_allele = 1)
    pop2_allele_counts = pop2_gt_array.count_alleles(max_allele = 1)
    
    # the number of (haploid) samples in each population
    pop1_n_haps = pop1_gt_array.n_samples * pop1_gt_array.ploidy
    pop2_n_haps = pop2_gt_array.n_samples * pop2_gt_array.ploidy
    
    # the total number of differences between populations summed across all sites
    total_diffs = (pop1_allele_counts[:,0] * pop2_allele_counts[:,1]) + (pop1_allele_counts[:,1] * pop2_allele_counts[:,0])
    total_diffs = np.sum(total_diffs, 0)
    
    # the total number of pairwise comparisons between sites
    total_comps = (pop1_allele_counts[:,0] + pop1_allele_counts[:,1]) * (pop2_allele_counts[:,0] + pop2_allele_counts[:,1])
    total_comps = np.sum(total_comps, 0)

    # the total count of possible pairwise comparisons at all sites
    total_possible = (pop1_n_haps * pop2_n_haps) * len(pop1_allele_counts)

    # the amount of missing is possible comps - actual ('total') comps
    total_missing = total_possible - total_comps
    
    # if there are valid data (comparisons between genotypes) at the site, compute average dxy
    # otherwise return NA
    if total_comps > 0:
        avg_dxy = total_diffs/total_comps 
    else:
        avg_dxy = "NA"
        
    return(avg_dxy, total_diffs, total_comps, total_missing)


# function for obtaining fst AND variance components via scikit allel function
# (need variance components for proper aggregation)
# for single sites, this is the final FST calculation
# in aggregation mode, we just want a,b,c and n_sites for aggregating and fst
def calc_fst(gt_array_fst, fst_pop_indicies, fst_type):
    
    # compute basic (multisite) FST via scikit allel
    
    # WC 84
    if fst_type == "wc":
        a, b, c = allel.weir_cockerham_fst(gt_array_fst, subpops = fst_pop_indicies)
        
        # compute variance component sums
        a = np.nansum(a).tolist()
        b = np.nansum(b).tolist()
        c = np.nansum(c).tolist()
        n_sites = len(gt_array_fst)
    
        # compute fst
        if (a + b + c) > 0:
            fst = a / (a + b + c)
        else:
            fst = "NA"
    
        return(fst, a, b, c, n_sites)
    
    # Hudson 92
    if fst_type == "hudson":
        
        # following scikit allel docs
        # allel counts for each population
        ac1 = gt_array_fst.count_alleles(subpop = fst_pop_indicies[0])
        ac2 = gt_array_fst.count_alleles(subpop = fst_pop_indicies[1])
        
        #hudson fst has two components (numerator & denominator)
        num, den = allel.hudson_fst(ac1, ac2)
        c = 0 # for compatibility with aggregation code for WC 84
        
        # compute variance component sums
        num = np.nansum(num).tolist()
        den = np.nansum(den).tolist()
        n_sites = len(gt_array_fst)
        
        # compute fst
        if (num + den) > 0:
            fst = num / den
        else:
            fst = "NA"
        
        # same abc format as WC84, where 'a' is the numerator and 
        # 'b' is the demoninator, and 'c' is a zero placeholder
        return(fst, num, den, c, n_sites)

# simplified version of above to handle the case 
# of per-site estimates of FST over whole chunks

def calc_fst_persite(gt_array_fst, fst_pop_indicies, fst_type):
    
    # compute basic (multisite) FST via scikit allel
    
    # WC 84
    if fst_type == "wc":
        a, b, c = allel.weir_cockerham_fst(gt_array_fst, subpops = fst_pop_indicies)

        fst = (np.sum(a, axis=1) / (np.sum(a, axis=1) + np.sum(b, axis=1) + np.sum(c, axis=1)))
    
        return(fst)
    
    # Hudson 92
    elif fst_type == "hudson":
        
        # following scikit allel docs
        # allel counts for each population
        ac1 = gt_array_fst.count_alleles(subpop = fst_pop_indicies[0])
        ac2 = gt_array_fst.count_alleles(subpop = fst_pop_indicies[1])
        
        #hudson fst has two components (numerator & denominator)
        num, den = allel.hudson_fst(ac1, ac2)
        
        fst = num/den

        return(fst)

def calc_watterson_theta(gt_array):

# counts of each of the two alleles at each site
    allele_counts = gt_array.count_alleles(max_allele = 1)

# counts of only variant sites by excluding sites with variant count 0
    variant_counts = allele_counts[allele_counts[:,1] != 0]

# for variant sites only, then all sites together, use Counter to generate dictionary
# where the key is the number of genotypes and value is number of sites with that many genotypes
    S = Counter(variant_counts[:,0] + variant_counts[:,1])
    N = Counter(allele_counts[:,0] + allele_counts[:,1])
#    S_keys = np.array([x for x in S.keys()])
#    S_values = np.array([y for y in S.values()])
    S_dict = np.array(tuple(S.items()))
    N_dict = np.array(tuple(N.items()))

#    N_array = np.array(tuple(N.items()))

# calculate watterson's theta as sum of equations for differing numbers of genotypes
# this is calculating Watterson's theta incorporating missing genotypes
#    start = perf_counter()
#    watterson_theta = np.sum((S[n]/np.sum(1 / np.arange(1, n))) for n in S)
#    weighted_sites = np.sum((N[n] * (n/max(N, key = N.get))) for n in N)
#    watterson_theta = np.sum((s/np.sum(1 / np.arange(1, n))) for n, s in S_dict)
#    watterson_theta = np.sum(np.divide(S_dict[:,1], np.sum(1 / np.arange(1, S_dict[:,0].all()))))
    watterson_theta = 0
    for n in S:
        a1 = np.sum(1 / np.arange(1, n))
        watterson_theta += S[n]/a1 
#    print(perf_counter() - start)
# calculate number of sites weighted by how many genotypes are missing in each site
# this allows calculation of an averaged Watterson's incorporating missing sites
#    start = perf_counter()
#    weighted_sites = np.sum((N[n] * (n/max(N))) for n in N)
    weighted_sites = np.sum(np.multiply(N_dict[:,1], (N_dict[:,0]/max(N))))
#    print(len(allele_counts))
#    weighted_sites = 0
#    for n in N:
#        weighted_sites += N[n] * (n/max(N))
#    print(perf_counter() - start)
# return averaged Watterson's theta, raw watterson's theta, and weighted site count
    return(watterson_theta/len(allele_counts), watterson_theta, weighted_sites)

def calc_tajima_d(gt_array):

# counts of each of the two alleles at each site
    allele_counts = gt_array.count_alleles(max_allele = 1)
#    mpd = allel.mean_pairwise_difference(allele_counts, fill = 0)
#    raw_pi = np.sum(mpd)

# counts of only variant sites by excluding sites with variant count 0
    variant_counts = allele_counts[allele_counts[:,1] != 0]
# for variant sites only, use Counter to generate dictionary
# where the key is the number of genotypes and value is number of sites with that many genotypes
    S = Counter(variant_counts[:,0] + variant_counts[:,1])
#    watterson_theta = np.sum((S[n]/np.sum(1 / np.arange(1, n))) for n in S)

    avg_pi = calc_pi(gt_array)[0]
    raw_pi = calc_pi(gt_array)[0] * len(allele_counts)
    avg_watterson_theta = calc_watterson_theta(gt_array)[0]
    raw_watterson_theta = calc_watterson_theta(gt_array)[1]

# calculate denominator for Tajima's D as in scikit-allel but looping to incoporate missing genotypes
#    start = perf_counter()
#    d_stdev = 0
    d_covar = 0
    d_stdev_denom = 0
#    for n, s in S.items():
# calculate watterson's theta as sum of equations for differing numbers of genotypes
# this is calculating Watterson's theta incorporating missing genotypes
#    watterson_theta = 0
#    for n, s in S.items():
#        a1 = np.sum(1 / np.arange(1, n))
#        watterson_theta += s/a1

# calculate denominator for Tajima's D as in scikit-allel but looping to incorporate missing genotypes
    d_stdev = 0
    for n, s in S.items():
        a1 = np.sum(1 / np.arange(1, n))
        a2 = np.sum(1 / (np.arange(1, n)**2))
        b1 = (n + 1) / (3 * (n - 1))
        b2 = 2 * (n**2 + n + 3) / (9 * n * (n - 1))
        c1 = b1 - (1 / a1)
        c2 = b2 - ((n + 2) / (a1 * n)) + (a2 / (a1**2))
        e1 = c1 / a1
        e2 = c2 / (a1**2 + a2)
#        d_stdev += np.sqrt((e1 * S[n]) + (e2 * S[n] * (S[n] - 1)))
#        d_covar += (e1 * s) + (e2 * s * (s - 1)) # add covariances not co standard deviations assuming same sample sizes
        d_covar += ((e1 * s) + (e2 * s * (s - 1))) * (n - 1) # don't assume same sample sizes (this has to be the case when there are missing genotypes)
        d_stdev_denom += n - 1 # variable sample sizes need summed denominator for standard deviation
#    d_stdev = np.sqrt(d_covar/len(S)) # assume same sample sizes for pooled variance
    d_stdev = np.sqrt(d_covar/d_stdev_denom) # don't assume same sample sizes for pooled variance
#    d_stdev = np.sum(np.sqrt((((((n + 1) / (3 * (n - 1))) - (1 / (np.sum(1 / np.arange(1, n))))) / (np.sum(1 / np.arange(1, n)))) * S[n]) + ((((2 * (n**2 + n + 3) / (9 * n * (n - 1))) - ((n + 2) / ((np.sum(1 / np.arange(1, n))) * n)) + ((np.sum(1 / (np.arange(1, n)**2))) / ((np.sum(1 / np.arange(1, n)))**2))) / ((np.sum(1 / np.arange(1, n)))**2 + (np.sum(1 / (np.arange(1, n)**2))))) * S[n] * (S[n] - 1))) for n in S)
#    print(perf_counter() - start)
    warnings.filterwarnings(action = 'error', category = RuntimeWarning)
    try:
        tajima_d = (raw_pi - raw_watterson_theta) / d_stdev
    except RuntimeWarning:
        tajima_d = 'NA'

# return Tajima's D calculation using raw pi and Watterson's theta calculations above
# also return the raw pi calculation, raw Watterson's theta, and standard deviation of their covariance individually
# note that the "raw" values of pi and Watterson's theta are needed for Tajima's D, not the ones incorporating sites
    return(tajima_d, raw_pi, avg_watterson_theta, d_stdev)
