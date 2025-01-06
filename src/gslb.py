#!/usr/bin/env python

import argparse
import os
import logging
import requests
import json
import time
from apscheduler.schedulers.blocking import BlockingScheduler
from kubernetes import client, config
from kubernetes.client.rest import ApiException
import jwt

import requests
import urllib3
from avi.sdk.avi_api import ApiSession

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
gslb_sched = BlockingScheduler()
# Disable certificate warnings

access_token = None
access_token_expiration = None

if hasattr(requests.packages.urllib3, 'disable_warnings'):
    requests.packages.urllib3.disable_warnings()

if hasattr(urllib3, 'disable_warnings'):
    urllib3.disable_warnings()


def filter_domains(entry):
    managed = managed_domains
    match = 0
    for domain in entry['domain_names']:
            for md in managed:
                if md in domain:
                    match += 1
    if match == len(entry['domain_names']):
        return True
    return False
                
def getSpaces(ucpClient):
    api = client.CustomObjectsApi(ucpClient)
    try:
        matched_spaces =[]
        ucp_spaces = api.list_namespaced_custom_object(group="spaces.tanzu.vmware.com", version="v1alpha1",plural="spaces",namespace="default")
        for space in ucp_spaces["items"]:
            name = space['metadata']['name']
            if "status" in space:
                if not any(cap["name"] == "ingress.tanzu.vmware.com" for cap in space["status"]["providedCapabilities"] ):
                    logging.info(f"space {name} does not have ingress capability, skipping")
                    continue
                for condition in space["status"]["conditions"]:
                    if condition["type"] == "Ready" and condition["status"]:
                        matched_spaces.append(name)  
        return matched_spaces

    except ApiException as e:
        logging.error(f"failed to get domainbinding data for {space}")
        raise

def get_domain_bindings(space,ucpClient):
    managed = managed_domains
    api = client.CustomObjectsApi(ucpClient)
    api.api_client.configuration.host = f"{ucpClient.configuration.host}/space/{space}"
    try:
        allocated= []
        bindings = api.list_namespaced_custom_object(group="networking.tanzu.vmware.com", version="v1alpha1",plural="domainbindings",namespace="default")
        for binding in bindings["items"]:
            if "status" in binding:
                for condition in binding["status"]["conditions"]:
                    if condition["type"] == "DomainAllocated" and condition["status"]:
                        for md in managed:
                            if md in binding["spec"]["domain"]:
                                allocated.append(binding)  
        return allocated

    except ApiException as e:
        logging.error(f"failed to get domainbinding data for {space}")
        raise


def getAccessToken(csp_host,csp_token):
    try:
        response = requests.post('https://%s/csp/gateway/am/api/auth/api-tokens/authorize?refresh_token=%s' % (csp_host,csp_token))
        response.raise_for_status()
    except Exception as e:
        logging.error(e)
        return None
    else:
        access_token = response.json()['access_token']
        expires_in = response.json()['expires_in']
        expire_time = time.time() + expires_in
        return access_token, expire_time


def set_global_token():
    logger.info("checking if token is expired")
    global access_token_expiration
    global access_token
    if time.time() > access_token_expiration:
        logger.info("udpating refresh token")
        access_token, access_token_expiration =  getAccessToken(csp_host,csp_token)

def get_global_token():
    return access_token
    

def run():
    
    global api_version
    gslb_data = {}

    set_global_token()
   
    if not api_version:
        # Discover Controller's version if no API version specified
        api = ApiSession.get_session(controller, user, password)
        api_version = api.remote_api_version['Version']
        api.delete_session()
        logger.info(f'Discovered Controller version {api_version}.')
    api = ApiSession.get_session(controller, user, password,
                                api_version=api_version)
    logger.info("creating ucp client")
    ucpConfig = client.Configuration()
    ucpConfig.verify_ssl = True
    ucpConfig.host = f"{tp_host}/org/{org_id}/project/{project_id}"
    ucpConfig.api_key = {"authorization": "Bearer " + access_token}
    ucpClient = client.ApiClient(ucpConfig)
    project_bindings = []
    if "*" in spaces:
        monit_spaces = getSpaces(ucpClient)
    else:
        monit_spaces = spaces
    for space in monit_spaces:
        ucpClient.configuration.host = f"{tp_host}/org/{org_id}/project/{project_id}"
        logger.info(f"generating space gslb data for {space}")
        try:
            domainBindings = get_domain_bindings(space,ucpClient)
            project_bindings +=domainBindings
            print(domainBindings)
        except ApiException as e:
          logging.error(f"unable to get any domain bindings for {space}: {e}")   
        
       

    desiredServices = []

    #reconcile domain bindings into unique domains and their pools members for now everything is round robin
    for binding in project_bindings:
        domain = binding["spec"]["domain"]
        members = []
        for address in binding["status"]["addresses"]:
            member = {
                "enabled": True,
                "ip":{
                    "addr": address["value"],
                    "type": "V4"
                }
            }
            if domain in gslb_data:
                if member not in gslb_data[domain]["record"]["groups"][0]["members"]:
                    gslb_data[domain]["record"]["groups"][0]["members"].append(member)
            else:
                members.append(member)
        
                record = {
                    "domain_names": [domain],
                    "name": domain,
                    "groups":[
                        {
                        "name": f"{domain}-pool",
                        "members": members
                        }
                    ]
                }
                gslb_data[domain] = {}
                gslb_data[domain]["record"] = record

    for _, serv in gslb_data.items():
        try:
            logger.debug(serv)
            #check if entry already exists
            record = serv['record']
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
                logger.info('creating')
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
                                        % (entry['name'], delres.status_code, delres.text))
                    logger.error(exception_string)
                    raise Exception(exception_string)
                else:
                    success_string = ('GSLB service deleted %s (%d:%s)'
                                        % (entry['name'], delres.status_code, delres.text))
                    logger.info(success_string)
    except Exception as ex:
            raise Exception('%s' % (ex))



if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('-c', '--controller',
                        help='FQDN or IP address of NSX ALB Controller', default=os.environ.get('AVI_CONTROLLER'))
    parser.add_argument('--tphost',
                        help='FQDN or IP address of the Tanzu Platform API,including the scheme',default=os.environ.get('TP_HOST'))
    parser.add_argument('--spaces',
                        help='comma separated list of spaces to watch, or * to watch all spaces that have ingress enabled',default=os.environ.get('SPACES'))
    parser.add_argument('--projectid',
                        help='id of the project to use',default=os.environ.get('PROJECT_ID'))
    parser.add_argument('--manageddomains',help='comma separated list of domains that should be managed',default=os.environ.get('MANAGED_DOMAINS'))
    parser.add_argument('-u', '--user', help='NSX ALB API Username',default=os.environ.get('AVI_USER'))
    parser.add_argument('-p', '--password', help='NSX ALB API Password',default=os.environ.get('AVI_PASSWORD'))
    parser.add_argument('--csptoken', help='CSP token for api calls',default=os.environ.get('CSP_TOKEN'))
    parser.add_argument('-t', '--tenant', help='Tenant',
                        default='admin')
    parser.add_argument('-x', '--apiversion', help='NSX ALB API version')



    args = parser.parse_args()

    if args:
        # If not specified on the command-line, prompt the user for the
        # controller IP address and/or password

        controller = args.controller
        user = args.user
        password = args.password
        tenant = args.tenant
        api_version = args.apiversion
        csp_token = None
        csp_host = None
        tp_host = args.tphost
        spaces_list = args.spaces
        project_id = args.projectid
        managed_domains = args.manageddomains.split(",")
        spaces = spaces_list.split(",")
        csp_token = args.csptoken
        csp_host = "console.tanzu.broadcom.com"
        
        try:
            logging.info("getting initial token")
            access_token, access_token_expiration = getAccessToken(csp_host,csp_token)
            if access_token is None:
                raise Exception("Request for access token failed.")
        except Exception as e:
            logging.error(e)
        else:
            logging.info("access token recieved")

        decoded = jwt.decode(access_token, options={"verify_signature": False})
        org_id = decoded['context_name']
        
        gslb_sched.add_job(id='run gslb job',func=run,trigger='interval',seconds=10)
        gslb_sched.start()

    else:
        parser.print_help()

    
