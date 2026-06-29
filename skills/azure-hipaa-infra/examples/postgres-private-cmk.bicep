targetScope = 'resourceGroup'

param location string = resourceGroup().location
param namePrefix string
param delegatedSubnetId string
param privateDnsZoneId string
param adminLogin string
@secure()
param adminPassword string
param userAssignedIdentityId string
param cmkKeyUriWithVersion string

var suffix = uniqueString(resourceGroup().id)
var postgresName = toLower('${namePrefix}-pg-${suffix}')

resource postgres 'Microsoft.DBforPostgreSQL/flexibleServers@2024-08-01' = {
  name: postgresName
  location: location
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${userAssignedIdentityId}': {}
    }
  }
  sku: {
    name: 'Standard_D2ds_v5'
    tier: 'GeneralPurpose'
  }
  properties: {
    version: '16'
    administratorLogin: adminLogin
    administratorLoginPassword: adminPassword
    storage: {
      storageSizeGB: 128
    }
    backup: {
      backupRetentionDays: 35
      geoRedundantBackup: 'Enabled'
    }
    highAvailability: {
      mode: 'ZoneRedundant'
    }
    network: {
      delegatedSubnetResourceId: delegatedSubnetId
      privateDnsZoneArmResourceId: privateDnsZoneId
    }
    dataEncryption: {
      type: 'AzureKeyVault'
      primaryKeyURI: cmkKeyUriWithVersion
      primaryUserAssignedIdentityId: userAssignedIdentityId
    }
  }
}

resource database 'Microsoft.DBforPostgreSQL/flexibleServers/databases@2024-08-01' = {
  parent: postgres
  name: 'app'
  properties: {
    charset: 'UTF8'
    collation: 'en_US.utf8'
  }
}

output postgresFqdn string = postgres.properties.fullyQualifiedDomainName
