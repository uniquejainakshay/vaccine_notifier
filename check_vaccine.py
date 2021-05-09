import requests
import traceback 
import json
from datetime import datetime, timedelta
from subprocess import PIPE, Popen
import time
import threading
import random
import telebot
import logging
import os
min_age_limits = [45, 18]

error_messages  = [
    "Please don't trouble me with invalid messages, else I will instruct vaccination centre, to inject you on your . . . <you_know_where>",
    "Please don't trouble me with invalid messages, or I'll trouble you back in the middle of the night",
    "Please don't trouble me with invalid messages, I'm not your spouse to listen to your rubbish ",
    "Please don't trouble me with invalid messages, or I will request your office to stop your WFH",
    "Please don't trouble me with invalid messages, or I will request your boss to give you work on weekends",
    "Please don't trouble me with invalid messages, Oh come on ! Is it so hard to get it right ? ",
    "Please don't trouble me with invalid messages, Can't you get it right ? I pity you "
]
help_str = """
Only following 2 commands are supported : 
/subscribe PINCODE YOUR_AGE : Will notify if vaccine is available at given PINCODE and your age. You can have as many subscriptions as possible
/subdistrict DISTRICT_CODE YOUR_AGE : Will notify if vaccine is available in given district and your age. You can have as many subscriptions as possible
/clear_subscriptions : Clears all your previous subscriptions

Use following APIs to find district code for your area:
https://cdn-api.co-vin.in/api/v2/admin/location/states
https://cdn-api.co-vin.in/api/v2/admin/location/districts/<state_id>

Dare you try sending any other command ! 
"""

failure_count = 0 
success_count = 0

registered_users = {}
subscriptions = {}
registered_users_fname = "users.json"
subscriptions_fname = "subscriptions.json"

passwd = "gimme_vaccine"
with open('token', 'r') as f:
    token = f.read().strip()
telegram_bot_instance = telebot.TeleBot(token)

def save_object_to_file(obj, fname):
    with open(fname, 'w') as f: 
        f.write(json.dumps(obj, indent=1))
    logging.debug("Saved to file : {}".format(fname))

def json_obj_from_file(fname):
    if not os.path.exists(fname):
        return {}
    with open(fname, 'r') as f: 
        obj = json.load(f)
    logging.info("Loaded from json file  : {}".format(fname))
    return obj

def add_subscription(string, user_id, is_district = False):
    district_code = -1
    pin = -1
    reply = ""
    failure = False
    try :
        l = [ int(i.strip()) for i in string.split(' ')[1:]]
        code , age = l
        if is_district:
            district_code = code
            if len(str(district_code)) != 3:
                reply += "Invalid pin {}".format(district_code)
                failure = True
        else:
            pin = code
            if len(str(pin)) != 6: 
                reply += "Invalid pin {}".format(pin)
                failure = True
        if age < min_age_limits[-1]:
            reply += "Age={} doesn't meet eligibility criteria".format(age)
            failure = True
    except: 
        reply += "Invalid arguments from user {}".format(string)
        failure = True

    if failure:
        return reply
    for i in min_age_limits:
        if i <= age:
            age = i
            break
    if is_district:
        subscription = "district_{}_{}".format(district_code, age)
    else:
        subscription = "{}_{}".format(pin, age)
    if subscription not in subscriptions: 
        subscriptions[subscription] = list()
    if user_id not in subscriptions[subscription] : 
        subscriptions[subscription].append(user_id)
    save_object_to_file(subscriptions, subscriptions_fname)
    return "Subscribed successfully to district code={} / pincode={} and age={}".format(district_code, pin, age)


def clear_all_subscriptions(user_id):
    empty = []
    for s in subscriptions:
        if user_id in subscriptions[s]:
            subscriptions[s].remove(user_id)
            if len(subscriptions[s]) == 0:
                empty.append(s)
    for s in empty:
        subscriptions.pop(s)
    save_object_to_file(subscriptions, subscriptions_fname)
    return "Cleared all subscriptions "

def start_telegram_bot_blocking():

    @telegram_bot_instance.message_handler(commands=['help'])
    def help_message(message):
        telegram_bot_instance.reply_to(message, help_str)
    
    def check_user(msg):
        if str(msg.from_user.id) not in registered_users:
            default_message_reply(msg)
            return False
        return True
        
    @telegram_bot_instance.message_handler(commands=['subscribe'])
    def help_message(message):
        if not check_user(message):
            return
        reply = add_subscription(message.text, message.from_user.id)
        telegram_bot_instance.reply_to(message, reply)
        logging.info("USER_INTERACTION name={} user_id={} msg={} reply={}".format(message.from_user.first_name, message.from_user.id, message.text , reply))

    @telegram_bot_instance.message_handler(commands=['subdistrict'])
    def help_message(message):
        if not check_user(message):
            return
        reply = add_subscription(message.text, message.from_user.id, True)
        telegram_bot_instance.reply_to(message, reply)
        logging.info("USER_INTERACTION name={} user_id={} msg={} reply={}".format(message.from_user.first_name, message.from_user.id, message.text , reply))

    @telegram_bot_instance.message_handler(commands=['clear_subscriptions'])
    def help_message(message):
        if not check_user(message):
            return
        reply = clear_all_subscriptions(message.from_user.id)
        telegram_bot_instance.reply_to(message, reply)
        logging.info("USER_INTERACTION name={} user_id={} msg={} reply={}".format(message.from_user.first_name,message.from_user.id, message.text, reply))

    @telegram_bot_instance.message_handler(func=lambda message: True)
    def default_message_reply(msg):
        if (str(msg.from_user.id) not in registered_users) and (msg.text != passwd): 
            telegram_bot_instance.reply_to(msg, "Please enter the password to continue")
        elif msg.text == passwd:
            registered_users[str(msg.from_user.id)] = "{} {}".format(msg.from_user.first_name, msg.from_user.last_name)
            save_object_to_file(registered_users, registered_users_fname)
            reply_text = "Welcome {} {} !".format(msg.from_user.first_name, msg.from_user.last_name)
            reply_text += help_str
            telegram_bot_instance.reply_to(msg, reply_text)
        else:
            idx = min(len(error_messages)-1, round(random.random() * len(error_messages)))
            telegram_bot_instance.reply_to(msg, error_messages[idx] + '\n' + help_str)

    telegram_bot_instance.polling()

def check_retry(url, count=10):
    global failure_count, success_count
    for i in range(count):
        try:
            response = requests.get(
                url, 
                headers={
                    "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_2) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.93 Safari/537.36"
                }
            )
            if response == 200:
                success_count += 1
            return response
        except:
            failure_count += 1
            pass
        time.sleep(1)
    logging.error("Max retries failure for URL : {}".format(url))
    logging.error("Stats: failure={} success={}".format(failure_count, success_count))
    return ""

    
def check_availability(date_str, pins):
    res = {}
    for pin in pins:
        url = "https://cdn-api.co-vin.in/api/v2/appointment/sessions/public/findByPin?pincode={}&date={}".format(pin, date_str)
        response = check_retry(url)
        if not response:
            continue
        data = response.json()
        for sess in data['sessions']:
            if sess['available_capacity'] <1:
                continue
            key = "{}_{}".format(sess['pincode'], sess['min_age_limit'])
            value = '''center={}
date={}
pin_code={}
available_capacity={}
vaccine={}
age_limit={}
                '''.format(sess['name']\
                 , sess['date'] , sess['pincode'], sess['available_capacity'], sess['vaccine'], sess['min_age_limit'])
            if key not in res:
                res[key] = [value]
            else:
                res[key].append(value)
        time.sleep(1)
    if len(res) > 0: 
        logging.debug(json.dumps(res, indent=1))
    return res

def check_district_level_availability(date_str, district_codes):
    res = {}
    for district_code in district_codes:
        url = f'https://cdn-api.co-vin.in/api/v2/appointment/sessions/calendarByDistrict?district_id={district_code}&date={date_str}'
        response = check_retry(url)
        if not response:
            continue
        data = response.json()
        centers = data['centers']
        for c in centers:
            sessions = c['sessions']
            for sess in sessions:
                if sess['available_capacity'] <= 0:
                    continue
                key = f'district_{district_code}_{sess["min_age_limit"]}'
                value = '''center={}
date={}
pin_code={}
available_capacity={}
vaccine={}
age_limit={}
                    '''.format(c['name']\
                    , sess['date'] , c['pincode'], sess['available_capacity'], sess['vaccine'], sess['min_age_limit'])
                if key not in res:
                    res[key] = [value]
                else:
                    res[key].append(value)
        time.sleep(1)
    if len(res) > 0: 
        logging.debug(json.dumps(res, indent=1))
    return res

def daterange(no_days=10):
    dat = datetime.today()
    for i in range(no_days):
        yield dat.strftime("%d-%m-%Y")
        dat = dat + timedelta(1)

def check_once():
    district_codes = list(set([int(i.split('_')[1]) for i in subscriptions if i.startswith("district_")]))
    pins = list(set([int(i.split('_')[0]) for i in subscriptions.keys() if not i.startswith("district_")]))
    logging.debug(f'Checking for pins {json.dumps(pins,indent=1)} and district codes {json.dumps(district_codes,indent=1)}')
    for datestr in daterange():
        res = check_availability(datestr, pins)
        res.update(check_district_level_availability(datestr, district_codes))
        for ss in res:
            if ss in subscriptions:
                for user_id in subscriptions[ss]:
                    logging.debug("Informing user name={} msg={}".format(registered_users[str(user_id)], res[ss]))
                    result_chunks = [res[ss][i:i + 5] for i in range(0, len(res[ss]), 5)]
                    for results in result_chunks:
                        serialized_results = "\n".join(results)
                        telegram_bot_instance.send_message(int(user_id), serialized_results)

def main(check_every_seconds=60):
    global registered_users, subscriptions
    logging.basicConfig(level=logging.INFO, filename='vaccine_checker.log', filemode='a', format='%(asctime)s %(name)s - %(levelname)s - %(message)s')
    logging.info("Script started")

    registered_users =  json_obj_from_file(registered_users_fname)
    subscriptions = json_obj_from_file(subscriptions_fname)

    t = threading.Thread(target=start_telegram_bot_blocking)
    t.start()

    while True: 
        try : 
            check_once()
        except Exception :
           print("Error " , datetime.now(), traceback.format_exc())
           pass 
        time.sleep(check_every_seconds)
    
    t.join()
    
    

if __name__ == "__main__":
	main()


