# Tanzu Platform AVI GSLB Automation

This repo contains an example of how to write automation to integrate with a GSLB that is not currently fully integrated with tanzu platform. Specifically this example is for AVI. The goal of this repo is to provide some basic automation that can be used to update the GSLB with information from Tanzu Spaces. 

## How it works

The python script included handles declarative management of GSLB entries. These entries are all based off of input from querying the tanzu platform for information about spaces and the routes configured in them. When running the script it will only manage domains that are in the `manageddomains` list, this way if the GSLB has entries that are not maintained through this process it will leave them alone. The script will iterate over the spaces provided and find the routes that have been configured. It will then determine where the spaces are scheduled and find the load balancer details for the `default-gateway` and generate a gslb config for avi with all of that information. Finally it will iterate over each gslb entry and either create or update that record. Then it will iterate over all existig entries in the GSLB and compare that to the list of declared entries in the yaml file. If there is a record that is not in the declared list and is part of the managed domain it will remove that entry from the GSLB.

All of this is done using the [python SDK for AVI](https://github.com/avinetworks/sdk). 


# Docker Usage

There is a pre-built docker image that can be used to run the script. simple run the below command with the cli args or env vars set.

```bash
docker run ghcr.io/warroyo/tpk8s-avi-gslb:1.0.0
```

## CLI Usage

```bash
usage: gslb.py [-h] [-c CONTROLLER] [--tmchost TMCHOST] [--tphost TPHOST] [--spaces SPACES] [--projectid PROJECTID]
               [--manageddomains MANAGEDDOMAINS] [--project PROJECT] [-u USER] [-p PASSWORD] [--csptoken CSPTOKEN] [-t TENANT]
               [-x APIVERSION]

optional arguments:
  -h, --help            show this help message and exit
  -c CONTROLLER, --controller CONTROLLER
                        FQDN or IP address of NSX ALB Controller
  --tmchost TMCHOST     FQDN or IP address of the TMC API, including the scheme
  --tphost TPHOST       FQDN or IP address of the Tanzu Platform API,including the scheme
  --spaces SPACES       comma separated list of spaces to watch
  --projectid PROJECTID
                        id of the project to use
  --manageddomains MANAGEDDOMAINS
                        comma separated list of domains that should be managed
  --project PROJECT     name of the project
  -u USER, --user USER  NSX ALB API Username
  -p PASSWORD, --password PASSWORD
                        NSX ALB API Password
  --csptoken CSPTOKEN   CSP token for api calls
  -t TENANT, --tenant TENANT
                        Tenant
  -x APIVERSION, --apiversion APIVERSION
                        NSX ALB API version
```

Environment variables can also be used in place of the cli flags

`AVI_CONTROLLER`
`PROJECT`
`TMC_HOST`
`TP_HOST`
`SPACES`
`MANAGED_DOMAINS`
`AVI_USER`
`AVI_PASSWORD`
`CSP_TOKEN`


## Usage

1. run the script

```bash
python gslb.py -c https://avi01.h2o-4-24460.h2o.vmware.com/  -p 'password' -u admin -f gslb-api-example.yaml
```


## Deploying in Tanzu Platform for K8s

This section outline how to deploy this as a part of a space in the platform. This is the recommended approach for running this.

