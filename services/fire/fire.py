#!/usr/bin/env python
# encoding:utf-8

import sys
import thread
import requests
import ConfigParser
import importlib
import json
import threading
import time
import datetime
from Queue import Queue
import logging
import coloredlogs

coloredlogs.install(level='debug', fmt='%(asctime)s %(levelname)s\t%(message)s')
logging.getLogger("urllib3").setLevel(logging.WARNING)

config = ConfigParser.ConfigParser()
config.read('./config.ini')  

# Job control
jobs = Queue()
WORKER_NUMBER = 1
EXPLOIT_TIMEOUT = 10
ROUND_TIME = 10
CTF_START_TIME = datetime.datetime(2018, 9, 16, 9, 0, 0, 0)

def create_log(exploit_url, target_url, flag):
    url = "http://%s:%d/api/%s/" % (
        config.get("sirius", "host"), 
        int(config.get("sirius", "port")), 
        "log",
    )
    data = {
        "exploit":exploit_url,
        "target":target_url,
        "flag":flag,
    }
    response = requests.post(url, headers={
        'Authorization': 'Bearer %s' % (config.get("sirius", "token")), 
    }, data=data)
    content = response.content
    log_id = json.loads(content)['id']
    return log_id, response.status_code

def submit(challenge, victim, attacker, flag, log_id):
    url = "http://%s:%d/submit" % (
        config.get("submittor", "host"),
        int(config.get("submittor", "port")),
    )
    params = {
        "challenge":challenge,
        "victim":victim,
        "attacker":attacker,
        "flag":flag,
        "id":log_id,
    }
    try:
        response = requests.get(url, params=params, timeout=1)
        return response.content
    except Exception as e:
        return e


def worker(wid):
    while True:
        job = jobs.get()
        description = "%s => %s [%s:%d]" % (
            job['team']['name'],
            job['challenge']['name'],
            job['host'],
            job['port'],
        )
        # logging.debug("[WORKER[%d]] %s"  % (wid, description))
        target = {
            "team":job['team'],
            "host":job['host'],
            "port":job['port'],
        }
        filename = job['filename'].replace(".py", "")
        enable = job['enable']

        if not enable:
            logging.warn("[WORKER(%d)] %s disabled" % (wid, description))
            continue

        module = importlib.import_module("exploits.%s" % (filename))
        result = module.Exploit(job['author'], job['challenge'], False).run(target)
        flag = result[1]
        log_id, status_code = create_log(
                job['exploit_url'],
                job['target_url'],
                flag,
        )
        if status_code != 201:
            logging.warn(content)
        if result[0]:
            logging.info("[WORKER(%d)] %s => %s" % (wid, description, flag))
            logging.debug(submit(
                job['challenge']['name'],
                job['team']['name'],
                "%s:%s" % (job['author'], job['filename']),
                flag,
                log_id,
            ))
        else:
            logging.error("[WORKER(%d)] %s => %s" % (wid, description, flag))

def query(model):
    url = "http://%s:%d/api/%s/" % (
        config.get("sirius", "host"), 
        int(config.get("sirius", "port")), 
        model
    )
    content = requests.get(url, headers={
        'Authorization': 'Bearer %s' % (config.get("sirius", "token")), 
    }).content
    return json.loads(content)

def cacheget(cache, url):
    if url in cache.keys():
        return cache[url]
    content = requests.get(url, headers={
        'Authorization': 'Bearer %s' % (config.get("sirius", "token")), 
    }).content
    cache[url] = content
    return content

def load_jobs():
    cache = dict()
    targets = query("target")
    i = 0
    for target in targets:
        i += 1
        target['target_url'] = "http://%s:%d/api/%s/%d/" % (
            config.get("sirius", "host"), 
            int(config.get("sirius", "port")), 
            "target",
            i,
        )
        cache_list = [
            'challenge',
            'team',
        ]
        for cache_key in cache_list:
            target[cache_key] = json.loads(cacheget(cache, target[cache_key]))

    exploits = query("exploit")
    i = 0
    for exploit in exploits:
        i += 1
        exploit['exploit_url'] = "http://%s:%d/api/%s/%d/" % (
            config.get("sirius", "host"), 
            int(config.get("sirius", "port")), 
            "exploit",
            i,
        )

        cache_list = [
            'challenge',
        ]
        for cache_key in cache_list:
            exploit[cache_key] = json.loads(cacheget(cache, exploit[cache_key]))
        for target in targets:
            if target['challenge'] == exploit['challenge']:
                job = {
                    "target_url":target['target_url'],
                    "exploit_url":exploit['exploit_url'],
                    "challenge":target['challenge'],
                    "enable":target['enable'],
                    "team":target['team'],
                    "host":target['host'],
                    "port":target['port'],
                    "filename":exploit['filename'],
                    "author":exploit['author'],
                    "priority":exploit['priority'],
                }
                jobs.put(job)

def start_workers():
    for i in range(WORKER_NUMBER):
        t = threading.Thread(target=worker, args=(i,))
        t.daemon = True
        t.start()

# Start works
start_workers()

# Job dispatcher
while True:
    round_start_time = datetime.datetime.now()
    logging.info(round_start_time)
    round_number = (round_start_time - CTF_START_TIME).seconds * 1.0 / ROUND_TIME
    logging.debug("The %d round started" % (round_number))
    # Generate jobs
    logging.debug("Loading victims...")
    load_jobs()
    logging.debug("Queue size: %d" % jobs.qsize())
    round_end_time = datetime.datetime.now()
    # Ensure sync with offical round
    logging.debug("Sleeping %d second for the next round" % (ROUND_TIME - (round_end_time - round_start_time).seconds))
    sleep_time = ROUND_TIME - (round_end_time - round_start_time).seconds
    sleeped_time = 0
    for i in range(sleep_time):
        time.sleep(1)
        sys.stderr.write("%d/%d\r" % (sleeped_time, sleep_time))
        sleeped_time += 1
