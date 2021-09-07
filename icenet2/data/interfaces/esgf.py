import argparse
import logging
import os
import re

import numpy as np
import xarray as xr

from icenet2.data.interfaces.downloader import ClimateDownloader
from icenet2.data.utils import esgf_search


class CMIP6Downloader(ClimateDownloader):
    TABLE_MAP = {
        'siconca': 'SIday',
        'tas': 'day',
        'ta': 'day',
        'tos': 'Oday',
        'psl': 'day',
        'rsus': 'day',
        'rsds': 'day',
        'zg': 'day',
        'uas': 'day',
        'vas': 'day',
        'ua': 'day',
    }

    GRID_MAP = {
        'siconca': 'gn',
        'tas': 'gn',
        'ta': 'gn',
        'tos': 'gr',
        'psl': 'gn',
        'rsus': 'gn',
        'rsds': 'gn',
        'zg': 'gn',
        'uas': 'gn',
        'vas': 'gn',
        'ua': 'gn',
    }

    ESGF_NODES = ("esgf-data3.ceda.ac.uk",
                  "esgf.bsc.es",
                  "esgf-data2.diasjp.net")

    def __init__(self,
                 *args,
                 source,
                 member,
                 nodes=ESGF_NODES,
                 experiments=('historical', 'ssp245'),
                 frequency="day",
                 table_map=TABLE_MAP,
                 grid_map=GRID_MAP,
                 grid_override=None,  # EC-Earth3 wants all 'gr'
                 years=[2012],
                 **kwargs):
        super().__init__(*args,
                         identifier="cmip6",
                         **kwargs)

        self._source = source
        self._member = member
        self._frequency = frequency
        self._experiments = experiments
        self._nodes = nodes
        self._years = years

        self._table_map = table_map
        self._grid_map = grid_map
        self._grid_map_override = grid_override

    def _get_dates_for_request(self):
        return [None]

    def _single_download(self, var_prefix, pressure, req_date):
        query = {
            'source_id': self._source,
            'member_id': self._member,
            'frequency': self._frequency,
            'variable_id': var_prefix,
            'table_id': self._table_map[var_prefix],
            'grid_label': self._grid_map_override
            if self._grid_map_override
            else self._grid_map[var_prefix],
        }

        var_name = "{}{}".format(var_prefix, "" if not pressure else pressure)
        output_name = "latlon_{}.{}.{}.nc".format(var_name,
                                                  self._source,
                                                  self._member)
        proc_name = re.sub(r'^latlon_', '', output_name)
        output_path = os.path.join(self.get_data_var_folder(var_name),
                                   output_name)
        proc_path = os.path.join(output_path, proc_name)

        if not os.path.exists(output_path) or \
                os.path.exists(os.path.join(output_path, proc_name)):
            logging.info("Querying ESGF")
            results = []
            for experiment_id in self._experiments:
                query['experiment_id'] = experiment_id

                for data_node in self._nodes:
                    query['data_node'] = data_node

                    node_results = esgf_search(**query)

                    if len(node_results):
                        logging.debug("Query: {}".format(query))
                        logging.debug("Found {}: {}".format(experiment_id,
                                                            node_results))
                        results.extend(node_results)
                        break

            logging.info("Found {} {} results from ESGF search".
                format(var_prefix, len(results)))

            # http://xarray.pydata.org/en/stable/user-guide/io.html?highlight=opendap#opendap
            # Avoid 500MB DAP request limit
            cmip6_da = xr.open_mfdataset(results,
                                         combine='by_coords',
                                         chunks={'time': '499MB'})[var_prefix]

            cmip6_da.sel(time=cmip6_da.time.dt.year.isin(self._years))

            if pressure:
                cmip6_da = cmip6_da.sel(plev=int(pressure * 100))

            logging.info("Retrieving and saving {}:".format(output_name))
            cmip6_da.compute()
            cmip6_da.to_netcdf(output_path)
        else:
            if not os.path.exists(proc_path):
                logging.info("{} already exists but is not processed".
                             format(output_path))
                self._files_downloaded.append(output_path)
            else:
                logging.info("{} processed file exists".format(proc_path))

    def additional_regrid_processing(self, datafile, cube_ease):
        (datafile_path, datafile_name) = os.path.split(datafile)
        var_name = datafile_path.split(os.sep)[-1]

        # Preprocessing
        if var_name == 'siconca':
            cube_ease.data[cube_ease.data > 500] = 0.
            cube_ease.data[:, self._masks.get_land_mask()] = 0.

        if self._source == 'MRI-ESM2-0':
            cube_ease.data = cube_ease.data / 100.
        elif var_name == 'tos':
            cube_ease.data[cube_ease.data > 500] = 0.
            cube_ease.data[:, self._masks.get_land_mask()] = 0.

        if cube_ease.data.dtype != np.float32:
            logging.info("Regrid processing, data type not float: {}".
                         format(cube_ease.data.dtype))
            cube_ease.data = cube_ease.data.astype(np.float32)


if __name__ == "__main__":
    logging.getLogger().setLevel(logging.DEBUG)
    logging.info("CMIP Downloader - direct module run")

    cmip = CMIP6Downloader(
        source="MRI-ESM2-0",
        member="r2i1p1f1",
        var_names=["zg"],
        pressure_levels=[[250]],
        dates=[None],
    )
    cmip.download()
#    cmip.regrid()
#    cmip.rotate_wind_data()
