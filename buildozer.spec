[app]
title = Dépôt Pharmaceutique
package.name = pharmacie
package.domain = org.monentreprise
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,db
version = 1.0
requirements = python3==3.11.5,hostpython3==3.11.5,kivy==2.3.0,pyjnius,android
title = Dépôt Pharmaceutique
android.minapi = 21
android.archs = arm64-v8a
android.accept_sdk_license = True
p4a.branch = v2024.01.21
orientation = portrait

[buildozer]
log_level = 2
