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

def filter_domains_create(entry):
            managed = managed_domains
            for domain in entry['record']['domain_names']:
                 for md in managed:
                     if md in domain:
                        return True
            return False

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
                

def get_fqdns(space,ucpClient):
    api = client.CustomObjectsApi(ucpClient)
    api.api_client.configuration.host = f"{ucpClient.configuration.host}/space/{space}"
    try:
        hostnames = []
        routes = api.list_namespaced_custom_object(group="gateway.networking.k8s.io", version="v1beta1",plural="httproutes",namespace="default")
        for route in routes['items']:
            for section in route['spec']['parentRefs']:
                if section['name'] == 'default-gateway':
                    hostname = section['sectionName'].removeprefix('https-').removeprefix('http-')
                    hostnames.append(hostname)
        return hostnames

    except ApiException as e:
        logging.error(f"failed to get httproute data for {space}")
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

        

# query tmc objects to get the ips of the load balancers for the default gateways
def get_service_details(cluster_name,namespace):
    lb_data = {}
    auth_header = f'Bearer {access_token}'
    try:
        service_request = requests.get(
            url=f"{tmc_host}/v1alpha1/clusters/{cluster_name}/objects?query=data.kind%3A%5B%27Service%27%5D+AND+data.namespaceName%3A{namespace}+AND+fullName.name%3Adefault-gateway-istio",
            headers={'Authorization': auth_header,'Content-type': 'application/json', 'x-project-id': project_id}
        )
    except requests.exceptions.RequestException as e:
       logging.error(f"unable to get service details for {cluster_name},{namespace}")
       raise 

    service = service_request.json()
    

    if 'objects' not in service:
        error_msg = "results of namespaces service has no data, there many not be any default-istio-gateways"
        logging.error(error_msg)
        raise Exception(error_msg)

    domain = service['objects'][0]['meta']['labels']['ingress.tanzu.vmware.com/domain']
    lb_data['domain'] = domain
    lb_info = service['objects'][0]['data']['objectService']['resourceService']['status']['loadBalancer']['ingress'][0]
    if 'ip' in lb_info:
        lb_data['address'] = lb_info['ip']
        return lb_data
    elif 'hostname' in lb_info:
        lb_data['address'] = lb_info['hostname']
        return lb_data
    else:
        error_msg = "no load balancer IP or hostanme for default-gateway"
        logging.error(error_msg)
        raise Exception(error_msg)

def get_space_data(space,ucpClient):
    api = client.CustomObjectsApi(ucpClient)
    try:
        ret = api.get_namespaced_custom_object(group="spaces.tanzu.vmware.com", version="v1alpha1",name=space,plural="spaces",namespace="default")
        return ret
    except ApiException as e:
        logging.error(f"failed to get space data for {space}")
        raise
    
def get_mn_list(space,ucpClient):
    api = client.CustomObjectsApi(ucpClient)
    try:
        label_selector = f"spaces.tanzu.vmware.com/space-name={space}"
        ret = api.list_namespaced_custom_object(label_selector=label_selector,group="spaces.tanzu.vmware.com", version="v1alpha1",plural="managednamespaces",namespace="default")
        return ret
    except ApiException as e:
        logging.error(f"failed to get managed namespaces data for {space}")
        raise

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
    gslb_data = {"gslb": []}

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

    for space in spaces:
        ucpClient.configuration.host = f"{tp_host}/org/{org_id}/project/{project_id}"
        logger.info(f"generating space gslb data for {space}")
        # space_object = get_space_data(space,ucpClient)
        space_gslb_data = {}
        spaceName = space
        space_gslb_data['space'] = spaceName
        
        namspaces = get_mn_list(space, ucpClient)

        fqdns = get_fqdns(space,ucpClient)
        baseDomain = ""
        members = []
        for mn in namspaces['items']:
            cluster = mn['status']['placement']['cluster']['name']
            lb_details = get_service_details(cluster,mn['metadata']['name'])
            lb_address = lb_details['address']
            baseDomain = lb_details['domain']
            member = {
                "enabled": True,
                "ip":{
                    "addr": lb_address,
                    "type": "V4"
                }
            }
            members.append(member)
        fqdns = [s + f".{baseDomain}" for s in fqdns]
        space_gslb_data['record'] = {
            "domain_names": fqdns,
            "name": f"{project_name}-{spaceName}",
            "groups":[
                {
                "name": f"{project_name}-{spaceName}-pool",
                "members": members
                }
            ]
        }
        gslb_data['gslb'].append(space_gslb_data)

    desiredServices = []
    filtered_services = filter(filter_domains_create,gslb_data['gslb'])
    for serv in filtered_services:
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
    parser.add_argument('--tmchost',
                        help='FQDN or IP address of the TMC API, including the scheme',default=os.environ.get('TMC_HOST'))
    parser.add_argument('--tphost',
                        help='FQDN or IP address of the Tanzu Platform API,including the scheme',default=os.environ.get('TP_HOST'))
    parser.add_argument('--spaces',
                        help='comma separated list of spaces to watch',default=os.environ.get('SPACES'))
    parser.add_argument('--projectid',
                        help='id of the project to use',default=os.environ.get('PROJECT_ID'))
    parser.add_argument('--manageddomains',help='comma separated list of domains that should be managed',default=os.environ.get('MANAGED_DOMAINS'))
    parser.add_argument('--project',
                        help='name of the project',default=os.environ.get('PROJECT'))
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
        tmc_host = args.tmchost
        tp_host = args.tphost
        spaces_list = args.spaces
        project_id = args.projectid
        project_name = args.project
        managed_domains = args.manageddomains.split(",")
        spaces = spaces_list.split(",")
        csp_token = args.csptoken
        csp_host = "console.cloud.vmware.com"
        
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

    
