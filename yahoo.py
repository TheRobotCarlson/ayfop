from bs4 import BeautifulSoup
import requests

from datetime import datetime, timedelta, date

import time

import pandas as pd
import numpy as np

import logging

import re
import math


# logger = logging.getLogger('root')
FORMAT = "[%(filename)s:%(lineno)s - %(funcName)20s() ] %(message)s"
logging.basicConfig(format=FORMAT)

# logging.debug('This is a debug message')
# logging.info('This is an info message')
# logging.warning('This is a warning message')
# logging.error('This is an error message')
# logging.critical('This is a critical message')


class YahooParsing:
    def __init__(self, ticker, expiration=None):
        self.ticker = ticker
        self.expiration = expiration

        self.fetch()

    def fetch(self):
        if self.expiration:
            self.options_url = "https://finance.yahoo.com/quote/{ticker}/options?date={expiration}".format(ticker=self.ticker, expiration=self.expiration)
        else:
            self.options_url = "https://finance.yahoo.com/quote/{ticker}/options".format(ticker=self.ticker)

        logging.debug("Options url parsed for {ticker}: {url}".format(ticker=self.ticker, url=self.options_url))
        
        self.page = requests.get(self.options_url).content
        self.soup = BeautifulSoup(self.page, "html.parser")

    def get_expirations(self):
        html = str(self.page)

        expirationString = html.find("\"expirationDates\"")

        startExpiration = html.find("[", expirationString)
        endExpiration = html.find("]", startExpiration)

        expirations = html[startExpiration + 1:endExpiration].split(",")
    
        return expirations

    def get_price(self):  
      
        html = str(self.page)

        priceLoc = html.find("\"price\"")

        # price
        entry = html.find("\"regularMarketPrice\"", priceLoc)
        searchStr = "\"fmt\""
        startPriceItem = html.find(searchStr, entry)
        startPrice = html.find("\"", startPriceItem + len(searchStr))
        endPrice = html.find("\"", startPrice + 1)
        price = float(html[startPrice + 1: endPrice])

        # price % change
        entry = html.find("\"regularMarketChangePercent\"", priceLoc)
        searchStr = "\"fmt\""
        startPriceItem = html.find(searchStr, entry)
        startPrice = html.find("\"", startPriceItem + len(searchStr))
        endPrice = html.find("\"", startPrice + 1)
        percentChange = float(html[startPrice + 1: endPrice - 1]) # have to get rid of the % sign    

        return {"price": price, "percentChange": percentChange}

    def get_options(self):

        options_tables = [] 
        tables = self.soup.find_all("table") 
        for i in range(len(tables)): 
            options_tables.append(tables[i].find_all("tr"))

        call_df = parse_table(options_tables[0]).sort_values("strike", ascending=True)
        put_df = parse_table(options_tables[1]).sort_values("strike", ascending=False)

        return {"calls": call_df, "puts": put_df}



def parse_table(table):
    columns = ["contract", "lastTradeDate", "strike", "lastPrice", "bid", "ask", "change", "percentChange", "volume", "openInterest", "iv"]
    
    # ['Contract Name', 'Last Trade Date', 'Strike', 'Last Price', 'Bid', 'Ask', 'Change', '% Change', 'Volume', 'Open Interest', 'Implied Volatility']
    types = {
        "strike": 'float64',
        "lastPrice": 'float64',
        "bid": 'float64',
        "ask": 'float64',
        "change": 'float64',
        "percentChange": 'float64',
        "volume": 'int64',
        "openInterest": 'int64',
        "iv": 'float64'
    }

    options = []
    for option in table[1:]:
        temp_call = [td.text for td in option.find_all("td")]
        options.append(temp_call)

    df = pd.DataFrame(data=options, columns=columns)
    df.replace({'-': '0'}, regex=False, inplace=True)
    df.replace({'\+(.+?)%': r"\1"}, regex=True, inplace=True)
    df.replace({'(.+?)%': r"\1"}, regex=True, inplace=True)
    df.replace({',': ''}, regex=True, inplace=True)
    df = df.astype(types)

    return df

def filter_otm_options(price, calls, puts):
    # I choose the strike price of the call to be consistent, 
    # but either will do, as long as the atm strike is the same
    otm_calls = calls[calls["strike"] > price]
    atm_call = otm_calls.iloc[0]
    atm_call_strike = atm_call['strike']

    otm_puts = puts[puts["strike"] <= atm_call_strike]
    atm_put = otm_puts.iloc[0]

    return {"atm_put": atm_put, "atm_call": atm_call, "otm_puts": otm_puts, "otm_calls": otm_calls}
    
def next_friday(given_date, distance):
    # week day is friday is 4 
    day_diff = (4 - given_date.weekday())
    day_diff += 0 if day_diff > 0 else 7
    day_shift = day_diff + distance
    return given_date + timedelta(days=day_shift)


def get_periods(period_date, expirations):

    period = ["weekly", "monthly", "yearly"]
    days = [7, 28, 364]

    exp_dates = {}
    day_index = 0
    
    for expiration in expirations:
        dt = datetime.utcfromtimestamp(int(expiration))

        # this is the actual expiration date option we have
        exp_date = date(dt.year, dt.month, dt.day)

        # what's the next friday X days away from period_date?
        friday = next_friday(period_date, days[day_index])

        # what's the first real expiration date after or on our friday?
        if friday <= exp_date:
            exp_dates[period[day_index]] = expiration

            day_index += 1

            if day_index >= len(days):
                break
    
    return exp_dates


if __name__ == "__main__":

    ticker = "SPY"
    data = YahooParsing(ticker)

    price_data = data.get_price()
    options = data.get_options()
    expirations = data.get_expirations()

    for expiration in expirations:
        print(expiration, datetime.utcfromtimestamp(int(expiration)).date())

    filtered_options = filter_otm_options(price=price_data["price"], calls=options["calls"], puts=options["puts"])

    print("atm call", filtered_options["atm_call"], sep="\n\n")
    print("atm put", filtered_options["atm_put"], sep="\n\n")
