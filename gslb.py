#!/usr/bin/env python

import argparse
import getpass
import yaml
import os
import logging

import requests
import urllib3
from avi.sdk.avi_api import ApiSession

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Disable certificate warnings

if hasattr(requests.packages.urllib3, 'disable_warnings'):
    requests.packages.urllib3.disable_warnings()

if hasattr(urllib3, 'disable_warnings'):
    urllib3.disable_warnings()

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('-c', '--controller',
                        help='FQDN or IP address of NSX ALB Controller')
    parser.add_argument('-u', '--user', help='NSX ALB API Username',
                        default='admin')
    parser.add_argument('-p', '--password', help='NSX ALB API Password')
    parser.add_argument('-t', '--tenant', help='Tenant',
                        default='admin')
    parser.add_argument('-x', '--apiversion', help='NSX ALB API version')

    parser.add_argument('-f','--file',help='File that contains the gslb service config')

    args = parser.parse_args()

    if args:
        # If not specified on the command-line, prompt the user for the
        # controller IP address and/or password

        controller = args.controller
        user = args.user
        password = args.password
        tenant = args.tenant
        api_version = args.apiversion
        serviceDef = args.file

        while not controller:
            controller = input('Controller:')

        while not password:
            password = getpass.getpass(f'Password for {user}@{controller}:')

        if not api_version:
            # Discover Controller's version if no API version specified

            api = ApiSession.get_session(controller, user, password)
            api_version = api.remote_api_version['Version']
            api.delete_session()
            print(f'Discovered Controller version {api_version}.')
        api = ApiSession.get_session(controller, user, password,
                                     api_version=api_version)
        
        with open(serviceDef, 'r') as file:
            apiDef = yaml.safe_load(file)

        def filter_domains(entry):
            managed = apiDef['managedDomains']
            if "record" in entry:
                entry = entry['record']
            for domain in  entry['domain_names']:
                 for md in managed:
                     if md not in domain:
                        return False
            return True


        desiredServices = []
        filtered_services = filter(filter_domains,apiDef['gslb'])
        for service in filtered_services:
            try:

                #check if entry already exists
                record = service['record']
                desiredServices.append(record['name'])
                entry = api.get_object_by_name('gslbservice',record['name'])
                if entry != None:
                    logger.info("GSLB record exists, updating")
                    r = api.put(f'gslbservice/{entry["uuid"]}',record)
                    if r.status_code > 300:
                        exception_string = ('Unable to update glsb-service %s (%d:%s)'
                                            % (record['name'], r.status_code, r.text))
                        logger.error(exception_string)
                        raise Exception(exception_string)
                    else:
                        success_string = ('GSLB service updated %s (%d:%s)'
                                            % (record['name'], r.status_code, r.text))
                        logger.info(success_string)

                else:
                    r = api.post('gslbservice',record)
                    if r.status_code > 300:
                        exception_string = ('Unable to create glsb-service %s (%d:%s)'
                                            % (record['name'], r.status_code, r.text))
                        logger.error(exception_string)
                        raise Exception(exception_string)
                    else:
                        success_string = ('GSLB service created %s (%d:%s)'
                                            % (record['name'], r.status_code, r.text))
                        logger.info(success_string)

            except Exception as ex:
                raise Exception('%s' % (ex))
            

        # delete any records that are no longer needed 
        try:
            entries = api.get_objects_iter('gslbservice')
            filtered_entries = filter(filter_domains,entries)
            for entry in filtered_entries:
                if entry['name'] not in desiredServices:
                    logger.info(f'deleteing {entry["name"]}')
                    delres = api.delete(f'gslbservice/{entry["uuid"]}')
                    if delres.status_code > 300:
                        exception_string = ('Unable to delete glsb-service %s (%d:%s)'
                                            % (entry['name'], r.status_code, r.text))
                        logger.error(exception_string)
                        raise Exception(exception_string)
                    else:
                        success_string = ('GSLB service deleted %s (%d:%s)'
                                            % (entry['name'], r.status_code, r.text))
                        logger.info(success_string)
        except Exception as ex:
                raise Exception('%s' % (ex))
  
        
            


    else:
        parser.print_help()

    
