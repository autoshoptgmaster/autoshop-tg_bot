from yandex_money import api

print(api.Wallet.build_obtain_token_url(
    client_id='11488C85A286C555F038E5BEEB40D7145D33895ED6E68ECC68C07DBEDFA920B7', redirect_uri='https://194.87.237.18:8443/ya_pay',
    scope=['account-info', 'operation-history', 'operation-details']) + '&response_type=code')

# Empty webserver index, return nothing, just http 200


wallet = api.Wallet(
    access_token='410015691952648.F2885C5DE257C9EF71296C9044C800E93B85C798A462249A32D1E75FA9C8B9B4E46CCC6F580F5095BEB87B2707E891CA954C86384DD3501954DD8AB86EE70C7E6FBF6611C9F507D46AFAE2F4E283CB514FCEAE9D63843DE4629D63158F408DADE73EA1C192EA850F2E4E12BEF50FED38F672D3023B722AFEC11EE7188A0A5215')
print(wallet.account_info())
print(wallet.operation_details(operation_id=410015691952648))
print(wallet.operation_history({'type': 'deposition', 'details': 'true'}))

