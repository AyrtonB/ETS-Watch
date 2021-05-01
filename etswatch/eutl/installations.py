# AUTOGENERATED! DO NOT EDIT! File to edit: nbs/02-eutl-installations.ipynb (unless otherwise specified).

__all__ = ['get_country_raw_search', 'extract_search_df', 'get_country_codes', 'get_installation_links_dataframe',
           'get_url_root_and_params', 'get_num_pages', 'extract_installation_allocations_df', 'retry_request',
           'get_installation_allocations_df', 'get_all_installation_allocations_df', 'get_installation_allocations_df']

# Cell
import pandas as pd
import numpy as np

import requests
from bs4 import BeautifulSoup as bs
import urllib.parse as urlparse
from urllib.parse import parse_qs

import re
from warnings import warn

from ipypb import track

# Cell
def get_country_raw_search(country_code='AT'):
    url = 'https://ec.europa.eu/clima/ets/nap.do'

    params = {
        'languageCode': 'en',
        'nap.registryCodeArray': country_code,
        'periodCode': '-1',
        'search': 'Search',
        'currentSortSettings': ''
    }

    r = requests.get(url, params=params)

    return r

# Cell
def extract_search_df(r):
    soup = bs(r.text)
    results_table = soup.find('table', attrs={'id': 'tblNapSearchResult'})

    df_search = (pd
                 .read_html(str(results_table))
                 [0]
                 .iloc[2:, :-3]
                 .reset_index(drop=True)
                 .T
                 .set_index(0)
                 .T
                 .reset_index(drop=True)
                 .rename(columns={
                     'National Administrator': 'country',
                     'EU ETS Phase': 'phase',
                     'For issuance to not new entrants': 'non_new_entrants',
                     'From NER': 'new_entrants_reserve'
                 })
                )

    df_search['installations_link'] = ['https://ec.europa.eu/'+a['href'] for a in soup.findAll('a', text=re.compile('Installations linked to this Allocation Table'))]

    return df_search

# Cell
def get_country_codes():
    r = get_country_raw_search()

    soup = bs(r.text)

    registry_code_to_country = {
        option['value']: option.text
        for option
        in soup.find('select', attrs={'name': 'nap.registryCodeArray'}).findAll('option')
    }

    return registry_code_to_country

# Cell
def get_installation_links_dataframe():
    df_search = pd.DataFrame()

    for registry_code in registry_code_to_country.keys():
        r = get_country_raw_search(registry_code)
        df_search_country = extract_search_df(r)
        df_search = df_search.append(df_search_country)

    df_search = df_search.reset_index(drop=True)
    null_values_present = df_search.isnull().sum().sum() > 0

    if null_values_present == True:
        warn('There are null values present in the dataframe')

    return df_search

# Cell
def get_url_root_and_params(installations_link):
    url_root = installations_link.split('?')[0]
    parsed = urlparse.urlparse(installations_link)
    params = {k: v[0] for k, v in parse_qs(parsed.query).items()}

    return url_root, params

# Cell
def get_num_pages(root_url, params):
    soup = bs(requests.get(root_url, params=params).text)
    soup_pn = soup.find('input', attrs={'name': 'resultList.lastPageNumber'})

    if soup_pn is not None:
        num_pages = int(soup_pn['value'])
    else:
        num_pages = 1

    return num_pages

# Cell
def extract_installation_allocations_df(r):
        soup = bs(r.text)
        table = soup.find('table', attrs={'id': 'tblNapList'})

        df_installation_allocations = (pd
                                       .read_html(str(table))
                                       [0]
                                       .drop([0, 1])
                                       .reset_index(drop=True)
                                       .T
                                       .set_index(0)
                                       .T
                                       .drop(columns=['Options'])
                                      )

        return df_installation_allocations

def retry_request(root_url, params, n_retries=5, **kwargs):
    for i in range(n_retries):
        try:
            r = requests.get(root_url, params=params, **kwargs)
            return r
        except Exception as e:
            continue

    raise e

def get_installation_allocations_df(root_url, params, n_retries=5):
    df_installation_allocations = pd.DataFrame()

    num_pages = get_num_pages(root_url, params)
    params['nextList'] = 'Next'

    for page_num in range(num_pages):
        params['resultList.currentPageNumber'] = page_num
        r = retry_request(root_url, params, n_retries=n_retries)

        df_installation_allocations_page = extract_installation_allocations_df(r)
        df_installation_allocations = df_installation_allocations.append(df_installation_allocations_page)

    df_installation_allocations = df_installation_allocations.reset_index(drop=True)

    return df_installation_allocations

# Cell
def get_all_installation_allocations_df(df_search):
    col_renaming_map = {
        'Installation ID': 'installation_id',
        'Installation Name': 'installation_name',
        'Address City': 'installation_city',
        'Account Holder Name': 'account_holder',
        'Account Status': 'account_status',
        'Permit ID': 'permit_id',
        'Status': 'status'
    }

    df_installation_allocations = pd.DataFrame()

    # Retrieving raw data
    for country in track(df_search['country'].unique()):
        df_installation_allocations_country = pd.DataFrame()
        country_installations_links = df_search.loc[df_search['country']==country, 'installations_link']

        for installations_link in track(country_installations_links, label=country):
            url_root, params = get_url_root_and_params(installations_link)
            df_installation_allocations_country_phase = get_installation_allocations_df(root_url, params)

            if df_installation_allocations_country.size > 0:
                df_installation_allocations_country = pd.merge(df_installation_allocations_country, df_installation_allocations_country_phase, how='outer', on=list(col_renaming_map.keys()))
            else:
                df_installation_allocations_country = df_installation_allocations_country_phase

        df_installation_allocations_country['country'] = country
        df_installation_allocations = df_installation_allocations.append(df_installation_allocations_country)

    # Collating update datetimes
    update_cols = df_installation_allocations.columns[df_installation_allocations.columns.str.contains('Latest Update')]
    df_installation_allocations['latest_update'] = df_installation_allocations[update_cols].fillna('').max(axis=1)
    df_installation_allocations = df_installation_allocations.drop(columns=update_cols)

    # Renaming columns
    df_installation_allocations = (df_installation_allocations
                                   .reset_index(drop=True)
                                   .rename(columns=col_renaming_map)
                                  )

    # Sorting column order
    non_year_cols = ['country'] + list(col_renaming_map.values()) + ['latest_update']
    year_cols = sorted(list(set(df_installation_allocations.columns) - set(non_year_cols)))
    df_installation_allocations = df_installation_allocations[non_year_cols+year_cols]

    # Dropping header rows
    idxs_to_drop = df_installation_allocations['permit_id'].str.contains('\*').replace(False, np.nan).dropna().index
    df_installation_allocations = df_installation_allocations.drop(idxs_to_drop)

    return df_installation_allocations

# Cell
def get_installation_allocations_df(data_dir='data', redownload=False):
    if not os.path.exists(data_dir):
        os.makedirs(data_dir)

    if redownload == True:
        df_search = get_installation_links_dataframe()
        df_installation_allocations = get_all_installation_allocations_df(df_search)
        df_installation_allocations.to_csv(f'{data_dir}/installation_allocations.csv', index=False)
    else:
        df_installation_allocations = pd.read_csv(f'{data_dir}/installation_allocations.csv')

    return df_installation_allocations