#!/usr/bin/env python

import argparse
import os
import logging
import requests
import json
import time
from apscheduler.schedulers.blocking import BlockingScheduler

import requests
import urllib3
from avi.sdk.avi_api import ApiSession

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
gslb_sched = BlockingScheduler()
# Disable certificate warnings

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
                

def get_fqdns(annotation):
    if annotation['key'] == 'ingress.tanzu.vmware.com/last-seen-fqdn':
        return True

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

        

def get_replicas(resource):
    if resource['relationships']['controlling']['resources']:
        return True

# query tmc objects to get the ips of the load balancers for the default gateways
def get_service_details(cluster_name,namespace):
    auth_header = f'Bearer {access_token}'
    service_request = requests.get(
        url=f"{tmc_host}/v1alpha1/clusters/{cluster_name}/objects?query=data.kind%3A%5B%27Service%27%5D+AND+data.namespaceName%3A{namespace}+AND+fullName.name%3Adefault-gateway-istio",
        headers={'Authorization': auth_header,'Content-type': 'application/json', 'x-project-id': project_id}
    )

    service = service_request.json()
    

    if len(service['objects']) != 1:
        error_msg = "results of namespaces service is not equal to 1, there many not be any default-istio-gateways or too many"
        logging.error(error_msg)
        raise Exception(error_msg)
    
    lb_info = service['objects'][0]['data']['objectService']['resourceService']['status']['loadBalancer']['ingress'][0]
    if 'ip' in lb_info:
        return lb_info['ip']
    elif 'hostname' in lb_info:
        return lb_info['hostname']
    else:
        error_msg = "no load balancer IP or hostanme for default-gateway"
        logging.error(error_msg)
        raise Exception(error_msg)

def get_space_data():
    auth_header = f'Bearer {access_token}'
    spaceData = requests.post(
        url=f"{tp_host}/hub/graphql",
        headers={'Authorization': auth_header,'Content-type': 'application/json; charset=utf-8'},
        data=json.dumps(spacesQuery)
    )
    spaces = spaceData.json()['data']['applicationEngineQuery']['querySpaces']['spaces']
    return spaces

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
                        help='id of the project to use')
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
        access_token = None
        access_token_expiration = None
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
        spacesQuery = {"operationName":"getSpaces","variables":{"spaceNames": spaces,"after":None,"first":10,"context":{"path":f"project/{project_id}","namespace":"default"}},"query":"query getSpaces($spaceNames: [String!], $after: String, $first: Int, $context: KubernetesResourceContextInput, $filter: QueryFilter) {\n  applicationEngineQuery(context: $context) {\n    querySpaces(name: $spaceNames, after: $after, first: $first, filter: $filter) {\n      count\n      totalCount\n      remainingCount\n      pageInfo {\n        hasNextPage\n        hasPreviousPage\n        startCursor\n        endCursor\n        __typename\n      }\n      spaces {\n        ...spaceInfo\n        ...spaceRelationshipInfo\n        __typename\n      }\n      __typename\n    }\n    __typename\n  }\n}\n\nfragment spaceInfo on KubernetesKindSpace {\n  name\n  id\n  metadata {\n    creationTimestamp\n    name\n    resourceVersion\n    annotations {\n      key\n      value\n      __typename\n    }\n    __typename\n  }\n  status {\n    resolvedProfiles {\n      name\n      reason\n      state\n      __typename\n    }\n    conditions {\n      lastTransitionTime\n      message\n      observedGeneration\n      reason\n      type\n      status\n      __typename\n    }\n    availabilityTargets {\n      name\n      readyReplicas\n      replicas\n      updatedReplicas\n      __typename\n    }\n    __typename\n  }\n  spec {\n    description\n    availabilityTargets {\n      name\n      replicas\n      __typename\n    }\n    template {\n      spec {\n        profiles {\n          name\n          values {\n            inline\n            __typename\n          }\n          __typename\n        }\n        resources {\n          limits {\n            key\n            value\n            __typename\n          }\n          requests {\n            key\n            value\n            __typename\n          }\n          __typename\n        }\n        __typename\n      }\n      __typename\n    }\n    updateStrategy {\n      type\n      __typename\n    }\n    __typename\n  }\n  yaml\n  __typename\n}\n\nfragment spaceRelationshipInfo on KubernetesKindSpace {\n  relationships {\n    controlling {\n      resources {\n        kind\n        name\n        ... on KubernetesKindManagedNamespaceSet {\n          relationships {\n            controlling {\n              resources {\n                kind\n                name\n                ... on KubernetesKindManagedNamespace {\n                  status {\n                    placement {\n                      cluster {\n                        name\n                        namespace\n                        __typename\n                      }\n                      __typename\n                    }\n                    __typename\n                  }\n                  __typename\n                }\n                __typename\n              }\n              __typename\n            }\n            __typename\n          }\n          __typename\n        }\n        __typename\n      }\n      __typename\n    }\n    __typename\n  }\n  __typename\n}\n"}

        def run():
            global access_token_expiration
            global access_token
            global api_version
            gslb_data = {"gslb": []}


            if time.time() > access_token_expiration:
                logger.info("udpating refresh token")
                access_token, access_token_expiration =  getAccessToken(csp_host,csp_token)

            if not api_version:
                # Discover Controller's version if no API version specified
                api = ApiSession.get_session(controller, user, password)
                api_version = api.remote_api_version['Version']
                api.delete_session()
                print(f'Discovered Controller version {api_version}.')
            api = ApiSession.get_session(controller, user, password,
                                        api_version=api_version)

       
            spaces  = get_space_data()
            for space in spaces:
                space_gslb_data = {}
                spaceName = space['name']
                space_gslb_data['space'] = spaceName
                
                
                fqdn_annot = filter(get_fqdns,space['metadata']['annotations'])
                fqdns = json.loads(list(fqdn_annot)[0]['value'])

                mns = filter(get_replicas,space['relationships']['controlling']['resources'])
                members = []
                for mn in next(mns)['relationships']['controlling']['resources']:
                    cluster = mn['status']['placement']['cluster']['name']
                    lb_address = get_service_details(cluster,mn['name'])
                    member = {
                        "enabled": True,
                        "ip":{
                            "addr": lb_address,
                            "type": "V4"
                        }
                    }
                    members.append(member)

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
        
        try:
            logging.info("getting initial token")
            access_token, access_token_expiration = getAccessToken(csp_host,csp_token)
            if access_token is None:
                raise Exception("Request for access token failed.")
        except Exception as e:
            logging.error(e)
        else:
            logging.info("access token recieved")

        

        
        gslb_sched.add_job(id='run gslb job',func=run,trigger='interval',seconds=10)
        gslb_sched.start()

    else:
        parser.print_help()

    
