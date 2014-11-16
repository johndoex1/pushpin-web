from map.models import Keys, Pushpin, Location
from django.core.exceptions import ValidationError
import requests
from urllib.parse import parse_qs
import json
import re
import pytz
from datetime import datetime

class ModuleException(Exception):
    pass

class Colors(object):
    N = '\033[m' # native
    R = '\033[31m' # red
    G = '\033[32m' # green
    O = '\033[33m' # orange
    B = '\033[34m' # blue

class Module:
    def __init__(self):
        return

    #======================================================
    # Key Management Methods
    #======================================================

    # retrieves keys from the database
    def getKey(self, name):
        # TODO one day add user control to keys/multiple users to app
        keys = Keys.objects.values(name)
        # potentially take list of values and return them all?

        if keys[0][name]:
            return keys[0][name]
        else:
            raise ModuleException("Key: " + name + " is not in database.")

    def addKey(self, name, key):
        # TODO: return only a user's keys (for multi-user use)
        keys = Keys.objects.get(user__username='test')
        setattr(keys, name, key)
        try: keys.full_clean()
        except ValidationError:
            raise ModuleException("Attempted to insert invalid key: " + name)
        keys.save()
        return

    #======================================================
    # Display Methods
    #======================================================

    def error(self, line):
        ''' formats and presents errors '''
        if not re.search('[.,;!?]$', line):
            line += '.'
        line = line[:1].upper() + line[1:]
        print('%s[!] %s%s' % (Colors.R, line, Colors.N))

    def output(self, line):
        '''Formats and presents normal output.'''
        print('%s[*]%s %s' % (Colors.B, Colors.N, line))

    #======================================================
    # Request Methods
    #======================================================

    def request(self, url, method="GET", timeout=None, payload=None, headers=None, cookiejar=None, auth=None, content='', redirect=True):
        if(method.lower() == "get"):
            r = requests.get(url, params=content, headers=headers, cookies=cookiejar, auth=auth, data=payload, timeout=timeout)
        elif(method.lower() == "post"):
            r = requests.post(url, params=content, headers=headers, cookies=cookiejar, auth=auth, data=payload, timeout=timeout)
        else:
            raise ModuleException("Only GET and POST requests are currently supported.")
            return None

        # TODO: Other things that would be nice to support:
        #request.user_agent = self.global_options['user-agent']
        #request.debug = self.global_options['debug']
        #request.proxy = self.global_options['proxy']

        if r.status_code == requests.codes.ok:
            return r
        else:
            raise ModuleException("Request to " + url + " returned with error " + str(r.status_code) + ".\n Response body: " + r.text)
            return None

    #======================================================
    # Request Methods
    #======================================================

    def get_twitter_oauth_token(self):
        try:
            return self.getKey('twitter_token')
        except:
            pass
        twitter_key = self.getKey('twitter_api')
        twitter_secret = self.getKey('twitter_secret')
        url = 'https://api.twitter.com/oauth2/token'
        auth = (twitter_key, twitter_secret)
        headers = {'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8'}
        payload = {'grant_type': 'client_credentials'}
        resp = self.request(url, method='POST', auth=auth, headers=headers, payload=payload)
        if 'errors' in resp.json():
            raise ModuleException('%s, %s' % (resp.json()['errors'][0]['message'], resp.json()['errors'][0]['label']))
        access_token = resp.json()['access_token']
        self.addKey('twitter_token', access_token)
        return access_token

    def search_twitter_api(self, payload):
        headers = {'Authorization': 'Bearer %s' % (self.get_twitter_oauth_token())}
        url = 'https://api.twitter.com/1.1/search/tweets.json'
        results = []
        while True:
            resp = self.request(url, content=payload, headers=headers)
            jsonobj = resp.json()
            for item in ['error', 'errors']:
                if item in jsonobj:
                    self.error(jsonobj[item])
                    raise ModuleException(jsonobj[item])
            results += jsonobj['statuses']
            if 'next_results' in jsonobj['search_metadata']:
                max_id = parse_qs(jsonobj['search_metadata']['next_results'][1:])['max_id'][0]
                payload['max_id'] = max_id
                continue
            break
        return results

    #======================================================
    # Database Methods
    #======================================================

    def createPin(self, source, screen_name, profile_name, profile_url, media_url, thumb_url, message, latitude, longitude, time):
        ## NOTE: this doesn't actually create a pushpin object, merely a dict that's ready to take a location (which requires a db hit) and then be easily turned into one
        if not type(time) is datetime:
            raise ModuleError("Supplied time must be in datetime format.")

        for (s,l) in Pushpin.SOURCES:
            # switch the verbose source out for the shorter DB version
            if l.lower() == source.lower():
                shortSrc = s
                break
            else:
                raise ModuleError("Invalid pushpin source: " + source)

        data = dict(
                source = shortSrc,
                screen_name = screen_name,
                profile_name = profile_name,
                profile_url = profile_url,
                media_url = media_url,
                thumb_url = thumb_url,
                message = message,
                latitude = float(latitude),
                longitude = float(longitude),
                time = time
                    )
        return data

    def addPins(self, locname, pins):
        location = Location.objects.get(name=locname)

        prep = [] # the Pushpin objects will go here
        for pin in pins:
            # add the location reference to each pin, then create the object
            if pin['time'].tzinfo is None:
                pin['time'] = pytz.utc.localize(pin['time'])
                # TODO: smarter localization based on coordinates

            prep.append(Pushpin(source = pin['source'],
                                date = pin['time'],
                                screen_name = pin['screen_name'],
                                profile_name = pin['profile_name'],
                                profile_url = pin['profile_url'],
                                media_url = pin['media_url'],
                                thumb_url = pin['thumb_url'],
                                message = pin['message'],
                                latitude = pin['latitude'],
                                longitude = pin['longitude'],
                                location = location
                               ))

        Pushpin.objects.bulk_create(prep)
