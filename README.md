# Tanzu Platform AVI GSLB Automation

This repo contains an example of how to write automation to integrate with a GSLB that is not currently fully integrated with tanzu platform. Specifically this example is for AVI. The goal of this repo is to provide some basic automation that can be used to update the GSLB with information from Tanzu Spaces. 

## How it works

The python script included handles declarative management of GSLB entries. These entries are all based off of a `yaml` file input. an example of the yaml input can be found in `gslb-api-example.yml`. When running the script it will only manage domains that are in the `managedDomains` list, this way if the GSLB has entries that are not maintained through this process it will leave them alone. The script will iterate over each gslb entry and either create or update that record. Then it will iterate over all existig entries in the GSLB and compare that to the list of declared entries in the yaml file. If there is a record that is not in the declared list and is part of the managed domain it will remove that entry from the GSLB.

All of this is done using the [python SDK for AVI](https://github.com/avinetworks/sdk). 

The intent is for this to be paired with another scipt that collects the needed GSLB endpoint information from the Tanzu platform APIs.

## API 

The API interface for this autmation is a yaml document. The basic structure can be found in `gslb-api-example.yml`

`project` -  the tanzu platform project
`managedDomains` - list of domains that this automation should manage. If the domain is in this list it will also clean up entries that are not needed. managed domains should be different per project. 
`gslb` - provides the list of GSLB service entries that need to be made
`gslb.space` -  the space name that the GSLB entry's app is running
`gslb.record` - the actual GSLB service entry. This is a direct copy of the AVI `gslbservice` api request. you can find the entire list of supported fields [here](https://avinetworks.com/docs/20.1/api-guide/GslbService/index.html#gslbservicePost).

## CLI Usage

```bash
usage: gslb.py [-h] [-c CONTROLLER] [-u USER] [-p PASSWORD] [-t TENANT] [-x APIVERSION] [-f FILE]

optional arguments:
  -h, --help            show this help message and exit
  -c CONTROLLER, --controller CONTROLLER
                        FQDN or IP address of NSX ALB Controller
  -u USER, --user USER  NSX ALB API Username
  -p PASSWORD, --password PASSWORD
                        NSX ALB API Password
  -t TENANT, --tenant TENANT
                        Tenant
  -x APIVERSION, --apiversion APIVERSION
                        NSX ALB API version
  -f FILE, --file FILE  File that contains the gslb service config
```

## Usage

1. create a `gslb-api.yml` file. this should match the api spec defined above
2. run the script with the needed inputs

```bash
python gslb.py -c https://avi01.h2o-4-24460.h2o.vmware.com/  -p 'password' -u admin -f gslb-api-example.yaml
```
