#!/usr/bin/env python3
"""
bundesAPI/handelsregister is the command-line interface for for the shared register of companies portal for the German federal states.
You can query, download, automate and much more, without using a web browser.
"""

import argparse
import pathlib
import sys

import mechanize
from bs4 import BeautifulSoup

# Dictionaries to map arguments to values
schlagwortOptionen = {
    "all": 1,
    "min": 2,
    "exact": 3
}


class GermanTradeRegister:
    def __init__(self, search_query, debug: bool, cache: bool):
        self.search_args = search_query
        self.debug_mode = debug
        self.cache_mode = cache
        self.browser = mechanize.Browser()

        self.browser.set_debug_http(debug)
        self.browser.set_debug_responses(debug)
        # self.browser.set_debug_redirects(True)

        self.browser.set_handle_robots(False)
        self.browser.set_handle_equiv(True)
        self.browser.set_handle_gzip(True)
        self.browser.set_handle_refresh(False)
        self.browser.set_handle_redirect(True)
        self.browser.set_handle_referer(True)

        self.browser.addheaders = [
            (
                "User-Agent",
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.5 Safari/605.1.15",
            ),
            ("Accept-Language", "de-DE,en;q=0.9"),
            ("Accept-Encoding", "gzip, deflate, br"),
            (
                "Accept",
                "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            ),
            ("Connection", "keep-alive"),
        ]

        self.cache_dir = pathlib.Path("cache")
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def open_startpage(self):
        self.browser.open("https://www.handelsregister.de", timeout=10)

    def cache_file_name(self, search_query_hash):
        return self.cache_dir / str(search_query_hash)

    def search_query_identifier(self):
        d = vars(self.search_args)
        query_identifier = ''

        for key, value in d.items():
            query_identifier += key + ":" + str(value) + "_"

        query_identifier = query_identifier[:-1]
        query_identifier = query_identifier.lower() + ".html"

        return query_identifier

    def search_company(self):
        search_query_identifier = self.search_query_identifier()
        cache_file_name = self.cache_file_name(search_query_identifier)

        if self.cache_mode and cache_file_name.exists():
            with open(cache_file_name, "r") as f:
                html = f.read()
                print("return cached content for %s" % self.search_args.schlagwoerter)
        else:
            # TODO implement token bucket to abide by rate limit
            # Use an atomic counter: https://gist.github.com/benhoyt/8c8a8d62debe8e5aa5340373f9c509c7
            self.browser.follow_link(text="Erweiterte Suche")

            if self.debug_mode:
                print(self.browser.title())

            self.browser.select_form(name="form")

            self.browser["form:schlagwoerter"] = self.search_args.schlagwoerter

            so_id = schlagwortOptionen.get(self.search_args.schlagwortOptionen)
            self.browser["form:schlagwortOptionen"] = [str(so_id)]

            ergebnisse_pro_seite = [self.search_args.ergebnisseProSeite]
            self.browser["form:ergebnisseProSeite_input"] = ergebnisse_pro_seite

            self.browser["form:NiederlassungSitz"] = self.search_args.niederlassung

            register_art = [self.search_args.registerArt]
            self.browser["form:registerArt_input"] = register_art

            register_gericht = [self.search_args.registerGericht]
            self.browser["form:registergericht_input"] = register_gericht

            self.browser["form:ort"] = self.search_args.ort

            response_result = self.browser.submit()

            if self.debug_mode:
                print(self.browser.title())

            html = response_result.read().decode("utf-8")
            with open(cache_file_name, "w") as f:
                f.write(html)

            # TODO catch the situation if there's more than one company?
            # TODO get all documents attached to the exact company
            # TODO parse useful information out of the PDFs
        return extract_companies_in_search_results(self, html)


def parse_result(self, result):
    cells = []

    for cell_num, cell in enumerate(result.find_all('td')):
        cells.append(cell.text.strip())

    # current_register_printout = self.browser.find_link(text='AD')

    search_result = {'court': cells[1],
                     'name': cells[2],
                     'city': cells[3],
                     'active': cells[4] == ("aktuell" or "currently registered"),
                     'documents': cells[5],  # TODO: retrieve all document links or binaries
                     'history': []
                     }
    history_start_index = 8
    history_end_index = len(cells)
    history_index = 1
    for i in range(history_start_index, history_end_index, 3):
        history_prefix = str(history_index) + ".) "
        if not cells[i].startswith(history_prefix):
            break
        if i + 1 == history_end_index:
            break
        if not cells[i + 1].startswith(history_prefix):
            break
        name = cells[i].replace(history_prefix, "")
        city = cells[i + 1].replace(history_prefix, "")
        history = {"position": history_index, "name": name, "city": city}
        search_result['history'].append(history)
        history_index += 1
    return search_result


def print_company_info(company):
    for tag in ('name', 'court', 'city', 'active'):
        print('%s: %s' % (tag, company.get(tag, '-')))
    print('history:')
    for history in company.get('history'):
        print("position: ", history['position'])
        print("name: ", history['name'])
        print("city: ", history['city'])
    print("-------------------------------")


def extract_companies_in_search_results(self, html):
    soup = BeautifulSoup(html, 'html.parser')
    grid = soup.find('table', role='grid')
    # self.browser.find_link(text='AD')

    results = []
    for result in grid.find_all('tr'):
        a = result.get('data-ri')
        if a is not None:
            if self.debug_mode:
                index = int(a)
                print('r[%d] %s' % (index, result))
            d = parse_result(self, result)
            results.append(d)
    return results


def parse_args(debug_mode: bool):
    # Parse arguments
    parser = argparse.ArgumentParser(description='A handelsregister CLI')

    parser.add_argument(
        "-s",
        "--schlagwoerter",
        help="Search for the provided keywords",
        required=False
    )

    parser.add_argument(
        "-so",
        "--schlagwortOptionen",
        choices=["all", "min", "exact"],
        default="min"
    )

    parser.add_argument(
        "-eps",
        "--ergebnisseProSeite",
        default="100"
    )

    parser.add_argument(
        "-nl",
        "--niederlassung",
        default="Mannheim"
    )

    parser.add_argument(
        "-ra",
        "--registerArt",
        choices=["alle", "HRA", "HRB", "GnR", "PR", "VR"],
        default="HRB"
    )

    parser.add_argument(
        "-rg",
        "--registerGericht"
    )

    parser.add_argument(
        "-rf",
        "--rechtsform"
    )

    parser.add_argument(
        "-o",
        "--ort",
        default="Mannheim"
    )

    # search_args = parser.parse_args()
    # print(type(search_args))
    # debug_arg = search_args.debug

    # Enable debugging if wanted
    if debug_mode:
        import logging
        logger = logging.getLogger("mechanize")
        logger.addHandler(logging.StreamHandler(sys.stdout))
        logger.setLevel(logging.DEBUG)

    return parser.parse_args()


if __name__ == "__main__":
    debug_mode = False
    cache_mode = False
    search_args = parse_args(debug_mode)
    trade_register = GermanTradeRegister(search_args, debug_mode, cache_mode)
    trade_register.open_startpage()
    companies = trade_register.search_company()
    if companies is not None:
        for c in companies:
            print_company_info(c)
