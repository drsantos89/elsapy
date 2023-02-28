"""The search module of elsapy.

Additional resources:
* https://github.com/ElsevierDev/elsapy
* https://dev.elsevier.com
* https://api.elsevier.com
"""

from urllib.parse import quote_plus as url_encode

import pandas as pd
import tqdm

from . import log_util
from .elsclient import ElsClient
from .utils import recast_df

logger = log_util.get_logger(__name__)


class ElsSearch:
    """Represents a search to one of the search."""

    # static / class variables
    _base_url = "https://api.elsevier.com/content/search/"
    _cursored_indexes = [
        "scopus",
    ]

    def __init__(self, query, index):
        """Initialize a search object with a query and target index."""
        self.query = query
        self.index = index
        self._cursor_supported = index in self._cursored_indexes
        self._uri = self._base_url + self.index + "?query=" + url_encode(self.query)
        self.results_df = pd.DataFrame()

    # properties
    @property
    def query(self) -> str:
        """Get the search query."""
        return self._query

    @query.setter
    def query(self, query: str) -> None:
        """Set the search query."""
        self._query = query

    @property
    def index(self) -> str:
        """Getsthe label of the index targeted by the search."""
        return self._index

    @index.setter
    def index(self, index: str) -> None:
        """Set the label of the index targeted by the search."""
        self._index = index

    @property
    def results(self) -> list:
        """Get the results for the search."""
        return self._results

    @property
    def tot_num_res(self) -> int:
        """Get the total number of results that exist in the index for this query.

        This number might be larger than can be retrieved and stored in a single
        ElsSearch object (i.e. 5,000).
        """
        return self._tot_num_res

    @property
    def num_res(self) -> int:
        """Get the number of results for this query.

        This number might be smaller than the number of results that exist in the index
        for the query.
        """
        return len(self.results)

    @property
    def uri(self) -> str:
        """Gets the request uri for the search."""
        return self._uri

    def _upper_limit_reached(self) -> bool:
        """Determine if the upper limit for retrieving results.

        Returns True if so, else False. Upper limit is 5,000 for indexes that don't
        support cursor-based pagination.
        """
        if self._cursor_supported:
            return False
        else:
            return self.num_res >= 5000

    def execute(
        self,
        els_client: ElsClient = None,
        get_all: bool = False,
        use_cursor: bool = False,
        view=None,
        count: int = 25,
    ) -> None:
        """Execute the search.

        If get_all = False (default), this retrieves the default number of results specified for the API.
        If get_all = True, multiple API calls will be made to iteratively get all results for the search, up to a maximum of 5,000.
        """
        # TODO: add exception handling
        url = self._uri
        if use_cursor:
            url += "&cursor=*"
        if view:
            url += f"&view={view}"
        if count:
            url += f"&count={count}"

        # retrieve search results
        api_response = els_client.exec_request(url)
        self._tot_num_res = int(
            api_response["search-results"]["opensearch:totalResults"]
        )

        # add progress bar
        progress = tqdm.tqdm(
            total=self._tot_num_res,
            position=0,
            desc="Retrieving results",
            unit="results",
        )

        # get results details
        self._results = api_response["search-results"]["entry"]
        if get_all is True:
            while (self.num_res < self.tot_num_res) and not self._upper_limit_reached():
                for e in api_response["search-results"]["link"]:
                    if e["@ref"] == "next":
                        next_url = e["@href"]
                api_response = els_client.exec_request(next_url)
                self._results += api_response["search-results"]["entry"]
                progress.update(count)
            progress.update(self.num_res - progress.n)
        progress.close()

        # convert to pandas dataframe
        self.results_df = recast_df(pd.DataFrame(self._results))

    def hasAllResults(self) -> bool:
        """Return true if the search object has retrieved all results for the querys."""
        return self.num_res is self.tot_num_res
