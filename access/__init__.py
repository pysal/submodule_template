__version__ = "1.0.0"
"""
:mod:`access` --- Accessibility Metrics
=================================================
"""

import pandas as pd
import geopandas as gpd
import warnings

from . import fca
from . import raam
from . import weights

class access():
    """
    Spatial Access Class

    Parameters
    ----------
    demand_df            : `pandas.DataFrame <https://pandas.pydata.org/pandas-docs/stable/reference/api/pandas.DataFrame.html>`_ or `geopandas.GeoDataFrame <http://geopandas.org/reference/geopandas.GeoDataFrame.html>`_
                           The origins dataframe, containing a location index and, optionally, a level of demand and geometry.
    demand_index         : {bool, str}
                           boolean of True indicates that the locations are already on the df index; 
                             otherwise the argument is a string containing the name of the column of `demand_df` that holds the origin ID.
    demand_value         : str
                           is the name of the column of `demand` that holds the aggregate demand at a location.
    supply_df            : `pandas.DataFrame <https://pandas.pydata.org/pandas-docs/stable/reference/api/pandas.DataFrame.html>`_ or `geopandas.GeoDataFrame <http://geopandas.org/reference/geopandas.GeoDataFrame.html>`_
                           The origins dataframe, containing a location index and, optionally, level of supply and geometry.
    supply_index         : {bool, str}
                           boolean of True indicates that the locations are already on the df index; 
                             otherwise the argument is a string containing the name of the column of `supply_df` that holds the origin ID.
    supply_value         : {str, list}
                           is the name of the column of `supply` that holds the aggregate supply at a location, or a list of such columns.
    cost_df              : `pandas.DataFrame <https://pandas.pydata.org/pandas-docs/stable/reference/api/pandas.DataFrame.html>`_
                           This dataframe contains a link from demand to supply locations, and a cost between them.
    cost_origin          : str
                           The column name of the index locations -- this is what will be grouped by.
    cost_dest            : str
                           The column name of the neighborhing demand locations -- this is what goes in the groups.
    cost_name            : {str, list}
                           The column(s) name of the travel cost(s).
    neighbor_cost_df     : `pandas.DataFrame <https://pandas.pydata.org/pandas-docs/stable/reference/api/pandas.DataFrame.html>`_
                           This dataframe contains a link from demand to neighbor locations, and a cost between them (running consumer to supplier).
    neighbor_cost_origin : str
                           The column name of the origin locations -- this is what will be grouped by.
    neighbor_cost_dest   : str
                           The column name of the destination locations -- this is what goes in the groups.
    neighbor_cost_name   : {str, list}
                           The column name(s) of the travel cost(s).

    Attributes
    ----------

    access               : pandas.DataFrame
                           All of the calculated access measures.
    access_metadata      : pandas.DataFrame
                           Lists currently-available measures of access.
    cost_metadata        : pandas.DataFrame
                           Describes each of the currently-available supply to demand costs.
    """


    def __init__(self, demand_df, demand_value, supply_df, supply_value,
                 demand_index = True, supply_index = True,
                 cost_df = None, cost_origin = None, cost_dest = None, cost_name = None,
                 neighbor_cost_df = None, neighbor_cost_origin = None, neighbor_cost_dest = None, neighbor_cost_name = None):

        """
        Initialize the class.

        Examples
        --------

        Import the base class and example data.

        >>> from access import access, examples as ex

        Inspect the example data:

        >>> ex.il_times.head()

        Using the example data, create an `access` object.

        >>> illinois_primary_care = \
                 access(demand_df = ex.il_pop,   demand_index = "geoid", demand_value = "pop",
                        supply_df = ex.il_doc,   supply_index = "geoid", 
                        supply_value = ["pc_physicians", "dentists"],
                        cost_df   = ex.il_times, cost_origin  = "origin", cost_dest = "dest")

        Attempt to calculate floating catchment area method:

        >>> illinois_primary_care.fca_ratio(max_cost = 60)
        TypeError: unsupported operand type(s) for +: 'int' and 'str'

        This failed, because we had not set a distance from users to their own neighbors.
        In the present case, `il_times` actually runs among 2010 Census Tracts, so we can use the same dataframe again,

        >>> illinois_primary_care.user_cost_neighbors(name = "cost", cost_df = ex.il_times, 
                                                      cost_origin = "origin", cost_dest = "dest")

        But we could have also have gotten a Euclidean distance for this.  First set the CRS to 3528, for Illinois (it already is).
        Note that this is "in place."

        >>> illinois_primary_care.to_crs(epsg = 3528)

        And now set the distances.

        >>> illinois_primary_care.euclidean_distance_neighbors(name = "euclidean")
          
        Calculate two-stage floating catchment method for all supply types, in a catchment of 60 minutes.

        >>> illinois_primary_care.two_stage_fca(max_cost = 60)
        {17031410900 : 0.1234, 17031836200 : 1.234, ... }
          
        Calculate RAAM with a tau parameter of 30 minutes, for every supply type (doctors and dentists).

        >>> illinois_primary_care.raam(name = "raam_tau30", tau = 30)
        {17031410900 : 0.1234, 17031836200 : 1.234, ... }

        Same thing, but with tau of 60 minutes.

        >>> illinois_primary_care.raam(name = "raam_tau60", tau = 60)
        {17031410900 : 0.1234, 17031836200 : 1.234, ... }

        Now doctors only, at 90 minutes:

        >>> illinois_primary_care.raam(supply = "pc_physicians", name = "raam_tau60", tau = 90)
        {17031410900 : 0.1234, 17031836200 : 1.234, ... }

        View all of the calculated types of access.

        >>> illinois_primary_care.access_metadata

        Create a weighted sum of multiple access types, from a dictionary.

        >>> illinois_primary_care.score({"pc_physicians_raam_tau60" : 1, "dentists_raam_tau30" : 0.2})
        """

        ### First all the dummy checks...

        if demand_index is not True and demand_index not in demand_df.columns:
            raise ValueError("demand_index must either be True -- or it must be a column of demand_df")

        if demand_value not in demand_df.columns:
            raise ValueError("demand_value must either be True -- or it must be a column of demand_df")

        if supply_index is not True and supply_index not in supply_df.columns:
            raise ValueError("supply_index must either be True -- or it must be a column of supply_df")

        if supply_value not in supply_df.columns:
            raise ValueError("supply_value must either be True -- or it must be a column of supply_df")

        if type(supply_value) is str and supply_value not in supply_df.columns:
            raise ValueError("supply_value must be a column of supply_df")

        if type(supply_value) is list:
            if any([sv not in supply_df.columns for sv in supply_value]):
                raise ValueError("supply_value must be columns of supply_df")

        if cost_df is not None:

          if cost_origin not in cost_df.columns:
              raise ValueError("cost_origin must be a column of cost_df")

          if cost_dest   not in cost_df.columns:
              raise ValueError("cost_dest must be a column of cost_df")

          if type(cost_name) is str and cost_name not in cost_df.columns:
              raise ValueError("cost_name must be a column of cost_df")

          if type(cost_name) is list:
              if any([cn not in cost_df.columns for cn in cost_name]):
                  raise ValueError("cost_name must be columns of cost_df")

        if neighbor_cost_df is not None:

          if neighbor_cost_origin not in neighbor_cost_df.columns:
              raise ValueError("neighbor_cost_origin must be a column of neighbor_cost_df")

          if neighbor_cost_dest   not in neighbor_cost_df.columns:
              raise ValueError("neighbor_cost_dest must be a column of neighbor_cost_df")

          if type(neighbor_cost_name) is str and neighbor_cost_name not in neighbor_cost_df.columns:
              raise ValueError("neighbor_cost_name must be a column of cost_df")

          if type(neighbor_cost_name) is list:
              if any([cn not in neighbor_cost_df.columns for cn in neighbor_cost_name]):
                  raise ValueError("neighbor_cost_names must be columns of cost_df")


        ### Now load the demand DFs.

        self.demand_df    = demand_df
        self.demand_value = demand_value
        if demand_index is not True: 
            self.demand_df.set_index(demand_index, inplace = True)
    
        ### And now the supply DFs.

        self.supply_df    = supply_df

        if type(supply_value) is str:
            self.supply_types = [supply_value]
        elif type(supply_value) is list:
            self.supply_types = supply_value
        else:
            raise ValueError("supply_value must be string or list of strings.")

        if supply_index is not True: 
            self.supply_df.set_index(supply_index, inplace = True)

        if cost_df is not None:
          
            self.cost_df     = cost_df
            self.cost_origin = cost_origin
            self.cost_dest   = cost_dest

            if type(cost_name) is str:
                self.cost_names = [cost_name]

            elif type(cost_name) is list:
                self.cost_names = cost_name

            else:
                raise ValueError("cost_name must be string or list of strings.")

            self.default_cost = self.cost_names[0]


        if neighbor_cost_df is not None:
          
            self.neighbor_cost_df     = neighbor_cost_df
            self.neighbor_cost_origin = neighbor_cost_origin
            self.neighbor_cost_dest   = neighbor_cost_dest
            self.neighbor_cost_name   = neighbor_cost_name

            if type(neighbor_cost_name) is str:
                self.neighbor_cost_names = [neighbor_cost_name]

            elif type(neighbor_cost_name) is list:
                self.neighbor_cost_names = neighbor_cost_name

            else:
                raise ValueError("neighbor_cost_name must be string or list of strings.")

            self.neighbor_default_cost = self.neighbor_cost_names[0]



        self.access = pd.DataFrame(index = self.supply_df.index)

        self.access_metadata = pd.DataFrame(columns = ["name", "distance", "function", "descriptor"])
        self.cost_metadata   = pd.DataFrame(columns = ["name", "type", "descriptor"])

        return


    def fca_ratio(self, name = "fca", demand_cost = None, supply_cost = None, max_cost = None):
        """
        Calculate the floating catchment area (buffer) access score.

        Parameters
        ----------
        name                : str 
                              Cutoff of cost values
        max_cost            : float
                              Cutoff of cost values

        Returns
        -------

        access              : pandas Series
                              Accessibility score for origin locations.

        """

        if demand_cost is None:

            demand_cost = self.neighbor_default_cost
            warnings.warn("Using default cost, {}.".format(demand_cost), Warning)

        if demand_cost not in self.neighbor_cost_names:

            raise ValueError("{} not an available neighbor cost.".format(demand_cost))

        if supply_cost is None:

            supply_cost = self.default_cost
            warnings.warn("Using default cost, {}.".format(supply_cost), Warning)

        if supply_cost not in self.cost_names:

            raise ValueError("{} not an available cost.".format(supply_cost))


        for s in self.supply_types:

            if "{}_{}.".format(name, s) in self.demand_df.columns:
                warnings.warn("Overwriting {}_{}.".format(name, s), Warning)

            series = fca.fca_ratio(demand_df = self.demand_df, 
                                                      demand_name = self.demand_value,
                                                      supply_df = self.supply_df,             
                                                      supply_name = s,
                                                      demand_cost_df = self.neighbor_cost_df, 
                                                      supply_cost_df = self.cost_df,          
                                                      demand_cost_origin = self.neighbor_cost_origin, demand_cost_dest = self.neighbor_cost_dest, demand_cost_name = demand_cost,
                                                      supply_cost_origin = self.cost_origin,          supply_cost_dest = self.cost_dest,          supply_cost_name = supply_cost,
                                                      max_cost = max_cost)
            reformatted_series = series.to_frame().rename({"FCA":name + "_" + s}, axis = 'columns')
            self.demand_df = self.demand_df.join(reformatted_series)
        return self.demand_df.filter(regex = "^" + name, axis = 1)


    def raam(self, tau = 1, cost = None): 
        """Calculate the rational agent access model cost.
        """

        if cost is None:
            cost = self.default_cost

    def two_stage_fca(self, name = "2sfca", cost = None, max_cost = None, weight_fn = None):
        """Calculate the two-stage floating catchment area access score.

        Parameters
        ----------
        name                : str 
                              Cutoff of cost values
        max_cost            : float
                              Cutoff of cost values

        Returns
        -------

        access              : pandas Series
                              Accessibility score for origin locations.

        """

        if cost is None:

            cost = self.default_cost
            warnings.warn("Using default cost, {}.".format(cost), Warning)

        if cost not in self.cost_names:

            raise ValueError("{} not an available cost.".format(cost))

        for s in self.supply_types:

            if "{}_{}.".format(name, s) in self.demand_df.columns:
                warnings.warn("Overwriting {}_{}.".format(name, s), Warning)
            
            series = fca.two_stage_fca(demand_df = self.demand_df, 
                                                      demand_name = self.demand_value,
                                                      supply_df = self.supply_df, 
                                                      supply_name = s,
                                                      cost_df = self.cost_df,    
                                                      cost_origin = self.cost_origin, cost_dest = self.cost_dest, cost_name = cost,
                                                      max_cost = max_cost, weight_fn = weight_fn)
            reformatted_series = series.to_frame().rename({"Rl":name + "_" + s}, axis = 'columns')
            self.demand_df = self.demand_df.join(reformatted_series)
        return self.demand_df.filter(regex = "^" + name, axis = 1)

    def three_stage_fca(self, name = "3sfca", cost = None, max_cost = None, weight_fn = None):
        """Calculate the three-stage floating catchment area access score.
        Parameters
        ----------
        name                : str 
                              Cutoff of cost values
        max_cost            : float
                              Cutoff of cost values

        Returns
        -------

        access              : pandas Series
                              Accessibility score for origin locations.

        """

        if cost is None:

            cost = self.default_cost
            warnings.warn("Using default cost, {}.".format(cost), Warning)

        if cost not in self.cost_names:

            raise ValueError("{} not an available cost.".format(cost))

        for s in self.supply_types:

            if "{}_{}.".format(name, s) in self.demand_df.columns:
                warnings.warn("Overwriting {}_{}.".format(name, s), Warning)
            
            series = fca.three_stage_fca(demand_df = self.demand_df, 
                                                      demand_name = self.demand_value,
                                                      supply_df = self.supply_df, 
                                                      supply_name = s,
                                                      cost_df = self.cost_df,    
                                                      cost_origin = self.cost_origin, cost_dest = self.cost_dest, cost_name = cost,
                                                      max_cost = max_cost, weight_fn = weight_fn)
            reformatted_series = series.to_frame().rename({"Rl":name + "_" + s}, axis = 'columns')
            self.demand_df = self.demand_df.join(reformatted_series)
        return self.demand_df.filter(regex = "^" + name, axis = 1)

    def score():
        """Weighted aggregate of multiple (already-calculated) access components."""
        pass

    def set_cost(self, new_cost):
        """Change the default cost measure."""

        if new_cost in self.cost_names:
            self.default_cost = new_cost

        else:
            raise ValueError("Tried to set cost not available in cost df")

    def set_neighbor_cost(self, new_cost):
        """Change the default cost measure."""

        if new_cost in self.neighbor_cost_names:
            self.neighbor_default_cost = new_cost

        else:
            raise ValueError("Tried to set cost not available in cost df")


    def user_cost():
        """Create a user cost, from demand to supply locations."""

        # Add it to the cost df.
        # Add it to the list of costs.

        pass

    def user_cost_neighbors():
        """Create a user cost, from supply locations to other supply locations."""

        # Add it to the list of costs.

        pass

    def euclidean_distance(self, name = "euclidean", threshold = 0, metric = 2, centroid_o = False, centroid_d = False):
        """Calculate the Euclidean distance from demand to supply locations.
           This is simply the geopandas `distance` function.  
           The user is responsible for putting the geometries into an appropriate reference system.
        """

        # Convert to centroids if so-specified
        # Calculate the distances.
        # Add it to the cost df.
        # Add it to the list of costs.

        pass

    def euclidean_distance_neighbors(name = "euclidean", threshold = 0, metric = 2, centroid = False):
        """Calculate the Euclidean distance among demand locations."""
        pass

