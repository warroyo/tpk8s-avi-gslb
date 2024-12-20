# Tanzu Platform AVI GSLB Automation

This repo contains an example of how to write automation to integrate with a GSLB that is not currently fully integrated with tanzu platform. Specifically this example is for AVI. The goal of this repo is to provide some basic automation that can be used to update the GSLB with information from Tanzu Spaces. 

## How it works

The python script included handles declarative management of GSLB entries. These entries are all based off of input from querying the tanzu platform for information about spaces and the routes configured in them. When running the script it will only manage domains that are in the `manageddomains` list, this way if the GSLB has entries that are not maintained through this process it will leave them alone. The script will iterate over all of the domainbindings in a project that match the domains that are configured to be watched. It will get the LB address details and fqdn from that domainbindings. Finally it will iterate over each gslb entry and either create or update that record. Then it will iterate over all existig entries in the GSLB and compare that to the list of currently desired entries. If there is a record that is not in the declared list and is part of the managed domain it will remove that entry from the GSLB.

All of this is done using the [python SDK for AVI](https://github.com/avinetworks/sdk). 


# Docker Usage

There is a pre-built docker image that can be used to run the script. simple run the below command with the cli args or env vars set.

```bash
docker run ghcr.io/warroyo/tpk8s-avi-gslb:2.0.0
```

## CLI Usage

```bash
usage: gslb.py [-h] [-c CONTROLLER] [--tphost TPHOST] [--spaces SPACES] [--projectid PROJECTID] [--manageddomains MANAGEDDOMAINS] [--project PROJECT] [-u USER] [-p PASSWORD]
               [--csptoken CSPTOKEN] [-t TENANT] [-x APIVERSION]

options:
  -h, --help            show this help message and exit
  -c CONTROLLER, --controller CONTROLLER
                        FQDN or IP address of NSX ALB Controller
  --tphost TPHOST       FQDN or IP address of the Tanzu Platform API,including the scheme
  --spaces SPACES       comma separated list of spaces to watch, or * to watch all spaces that have ingress enabled
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
`TP_HOST`
`SPACES`
`MANAGED_DOMAINS`
`AVI_USER`
`AVI_PASSWORD`
`CSP_TOKEN`
`PROJECT_ID`
`TENANT`


## Watching Spaces

There is the option to provide a comma seperated list of spaces to the `SPACES` env var or you can use '*' whcih will watch all spaces that have the ingress capabiltiy.

## Usage

1. run the script

```bash
python gslb.py -c https://avi01.h2o-4-24460.h2o.vmware.com/  -p 'password' -u admin
```


## Deploying in Tanzu Platform for K8s

This section outline how to deploy this as a part of a space in the platform. This is the recommended approach for running this.

###  Deploy the controller to a space

1. clone repo and checkout the right version tag

```bash
git clone https://github.com/warroyo/tpk8s-avi-gslb 
git checkout v2.1.0
```

2. connect to your project
```bash
tanzu project use <project>
```

3. create a profile called `byo-gslb-controller` . This brings in the minimal capabilties needed to deploy. 
   
```bash
tanzu deploy --only  plaftorm-configs/gslb-controller-space-profile.yml
```

4. create a space using the profile and make sure to select an AVT that will have access to the avi controller
5. `tanzu space use <previous space>`
6. copy the `secret-example.yml` into the `.tanzu/config` directory and rename it `secret.yml`
7. Update all of the values in the `secret.yml` 
8. `tanzu space use <your-space>`
9. `tanzu deploy --from-build ./deploy`


## Using with spaces


### Create self managed DNS domain

in the networking section of the admin page, create a new domain and choose manage my own DNS". This should be one of the domains that are configured to be managed by the controller

### Deploy and app and create a  domain binding

After the app is deployed create a domain binding to the domain you previsouly created and it will be picked up by the controller. 

### Validating it works

you can check the logs on the gslb-controller pod in the cluster to make sure it is working. Also check the gslb entries in AVI.
