#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Billing / shipping address pool per country."""
import random
from dataclasses import dataclass
from typing import Dict, List

from .constants import (
    EMAIL_DOMAINS, FIRST_NAMES, LAST_NAMES, SHIPPING_FALLBACK_ORDER,
)


@dataclass
class Address:
    first_name: str
    last_name: str
    address1: str
    address2: str
    city: str
    country_code: str
    zone_code: str
    postal_code: str
    phone: str
    email_domain: str = "gmail.com"


COUNTRY_ADDRESSES: Dict[str, Address] = {
    "US":     Address("james","anderson","428 W 45th St","Apt 4B","New York","US","NY","10036","+12125550100","gmail.com"),
    "US-CA":  Address("michael","johnson","123 Hollywood Blvd","Suite 100","Los Angeles","US","CA","90028","+13235550100","yahoo.com"),
    "US-TX":  Address("robert","williams","456 Main St","","Houston","US","TX","77002","+17135550100","outlook.com"),
    "US-FL":  Address("david","brown","789 Ocean Dr","Apt 12","Miami","US","FL","33139","+13055550100","hotmail.com"),
    "CA":     Address("john","smith","200 Kent St","","Ottawa","CA","ON","K1A 0G9","+16135550100","gmail.com"),
    "CA-BC":  Address("william","davis","789 Granville St","Floor 5","Vancouver","CA","BC","V6Z 1K9","+16045550100","gmail.com"),
    "GB":     Address("james","wilson","10 Downing St","","London","GB","ENG","SW1A 2AA","+442012345678","gmail.com"),
    "GB-MAN": Address("oliver","martinez","123 Deansgate","Apt 3B","Manchester","GB","ENG","M3 4BQ","+441619876543","outlook.com"),
    "AU":     Address("thomas","taylor","1 George St","","Sydney","AU","NSW","2000","+61212345678","gmail.com"),
    "AU-MEL": Address("daniel","anderson","100 Collins St","Level 10","Melbourne","AU","VIC","3000","+61398765432","yahoo.com"),
    "DE":     Address("lucas","thomas","Friedrichstr 100","","Berlin","DE","BE","10117","+493012345678","gmail.com"),
    "DE-MUC": Address("felix","schmidt","Marienplatz 1","","Munich","DE","BY","80331","+49891234567","gmail.com"),
    "FR":     Address("hugo","bernard","10 Rue de Rivoli","","Paris","FR","IDF","75001","+33112345678","gmail.com"),
    "FR-LY":  Address("louis","petit","15 Rue de la Republique","","Lyon","FR","ARA","69001","+33487654321","outlook.com"),
    "NZ":     Address("jack","wilson","1 Queen St","","Auckland","NZ","AUK","1010","+6491234567","gmail.com"),
    "NZ-WLG": Address("liam","brown","100 Willis St","Floor 2","Wellington","NZ","WGN","6011","+6449876543","gmail.com"),
    "IE":     Address("sean","murphy","1 Grafton St","","Dublin","IE","D","D02 Y006","+35311234567","gmail.com"),
    "IE-CORK":Address("patrick","kelly","100 Patrick St","","Cork","IE","CO","T12 XY88","+35321456789","gmail.com"),
    "NL":     Address("bas","jansen","Dam 1","","Amsterdam","NL","NH","1012 JS","+31201234567","gmail.com"),
    "ES":     Address("carlos","garcia","Calle Mayor 1","","Madrid","ES","M","28013","+34912345678","gmail.com"),
    "IT":     Address("marco","rossi","Via Roma 1","","Rome","IT","RM","00184","+39061234567","gmail.com"),
    "SE":     Address("erik","andersson","Vasagatan 1","","Stockholm","SE","AB","111 20","+468123456","gmail.com"),
    "NO":     Address("olav","hansen","Karl Johans gate 1","","Oslo","NO","03","0154","+4721234567","gmail.com"),
    "DK":     Address("lars","nielsen","Stroget 1","","Copenhagen","DK","84","1457","+4531234567","gmail.com"),
    "FI":     Address("jussi","korhonen","Mannerheimintie 1","","Helsinki","FI","18","00100","+35891234567","gmail.com"),
    "BE":     Address("jan","peeters","Grote Markt 1","","Brussels","BE","BRU","1000","+3221234567","gmail.com"),
    "CH":     Address("hans","weber","Bahnhofstrasse 1","","Zurich","CH","ZH","8001","+41441234567","gmail.com"),
    "AT":     Address("markus","gruber","Stephansplatz 1","","Vienna","AT","9","1010","+4312345678","gmail.com"),
    "JP":     Address("takashi","yamamoto","1-1-1 Marunouchi","","Tokyo","JP","13","100-0005","+81312345678","gmail.com"),
    "SG":     Address("wei","tan","1 Raffles Place","#01-01","Singapore","SG","01","048616","+6561234567","gmail.com"),
    "AE":     Address("ahmed","al-mansouri","Sheikh Zayed Road 1","","Dubai","AE","DU","12345","+97141234567","gmail.com"),
}


def generate_random_email() -> str:
    name = random.choice(FIRST_NAMES) + random.choice(LAST_NAMES) + str(random.randint(1, 999))
    return f"{name}@{random.choice(EMAIL_DOMAINS)}"


def address_for_country(country: str) -> Address:
    if country in COUNTRY_ADDRESSES:
        return COUNTRY_ADDRESSES[country]
    base = country[:2] if len(country) > 2 else country
    if base in COUNTRY_ADDRESSES:
        return COUNTRY_ADDRESSES[base]
    return COUNTRY_ADDRESSES["US"]


def get_fallback_addresses(exclude_country: str = "US") -> List[Address]:
    out = []
    for code in SHIPPING_FALLBACK_ORDER:
        if code.upper() != exclude_country.upper() and code in COUNTRY_ADDRESSES:
            out.append(COUNTRY_ADDRESSES[code])
    return out
