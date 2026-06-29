targetScope = 'resourceGroup'

param location string = resourceGroup().location
param siteName string
param planName string
param containerImage string
param userAssignedIdentityId string
param userAssignedIdentityClientId string
param integrationSubnetId string
param privateEndpointSubnetId string
param vnetId string
param aadClientId string
param keyVaultUri string

resource plan 'Microsoft.Web/serverfarms@2023-12-01' = {
  name: planName
  location: location
  kind: 'linux'
  sku: { name: 'P1v3' }
  properties: { reserved: true }
}

func kvRef(vaultUri string, secretName string) string => '@Microsoft.KeyVault(SecretUri=${vaultUri}secrets/${secretName})'

resource site 'Microsoft.Web/sites@2023-12-01' = {
  name: siteName
  location: location
  kind: 'app,linux,container'
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${userAssignedIdentityId}': {} }
  }
  properties: {
    serverFarmId: plan.id
    httpsOnly: true
    publicNetworkAccess: 'Disabled'
    keyVaultReferenceIdentity: userAssignedIdentityId
    virtualNetworkSubnetId: integrationSubnetId
    vnetRouteAllEnabled: true
    siteConfig: {
      linuxFxVersion: 'DOCKER|${containerImage}'
      alwaysOn: true
      ftpsState: 'Disabled'
      healthCheckPath: '/healthz'
      acrUseManagedIdentityCreds: true
      acrUserManagedIdentityID: userAssignedIdentityClientId
      appSettings: [
        { name: 'AZURE_CLIENT_ID', value: userAssignedIdentityClientId }
        { name: 'DATABASE_URL', value: kvRef(keyVaultUri, 'database-url') }
      ]
    }
  }
}

resource siteAuth 'Microsoft.Web/sites/config@2023-12-01' = if (!empty(aadClientId)) {
  parent: site
  name: 'authsettingsV2'
  properties: {
    platform: { enabled: true }
    globalValidation: {
      requireAuthentication: true
      unauthenticatedClientAction: 'RedirectToLoginPage'
      redirectToProvider: 'azureactivedirectory'
      excludedPaths: ['/healthz']
    }
    identityProviders: {
      azureActiveDirectory: {
        enabled: true
        registration: {
          clientId: aadClientId
          clientSecretSettingName: 'MICROSOFT_PROVIDER_AUTHENTICATION_SECRET'
          openIdIssuer: '${environment().authentication.loginEndpoint}${tenant().tenantId}/v2.0'
        }
        validation: { allowedAudiences: [aadClientId, 'api://${aadClientId}'] }
      }
    }
    login: { tokenStore: { enabled: true } }
  }
}

resource siteDnsZone 'Microsoft.Network/privateDnsZones@2020-06-01' = {
  name: 'privatelink.azurewebsites.net'
  location: 'global'
}

resource siteDnsLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2020-06-01' = {
  parent: siteDnsZone
  name: 'vnet-link'
  location: 'global'
  properties: { registrationEnabled: false, virtualNetwork: { id: vnetId } }
}

resource sitePe 'Microsoft.Network/privateEndpoints@2023-11-01' = {
  name: '${siteName}-pe'
  location: location
  properties: {
    subnet: { id: privateEndpointSubnetId }
    privateLinkServiceConnections: [
      { name: 'sites', properties: { privateLinkServiceId: site.id, groupIds: ['sites'] } }
    ]
  }
}

resource sitePeDns 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2023-11-01' = {
  parent: sitePe
  name: 'default'
  properties: { privateDnsZoneConfigs: [{ name: 'sites', properties: { privateDnsZoneId: siteDnsZone.id } }] }
}

output privateSiteHostName string = site.properties.defaultHostName
