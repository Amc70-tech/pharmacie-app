[app]
title = Pharmacie
package.name = pharmacie
package.domain = org.monentreprise
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,db
version = 1.0
requirements = python3==3.10.13,kivy==2.3.0,cython==3.0.10
android.permissions = WRITE_EXTERNAL_STORAGE,READ_EXTERNAL_STORAGE
android.api = 30
android.minapi = 21
android.archs = arm64-v8a
android.accept_sdk_license = True
android.ndk = 25b
android.gradle_options = --no-daemon --stacktrace
android.add_gradle_properties = org.gradle.jvmargs=-Xmx2048m -Dfile.encoding=UTF-8
p4a.branch = v2024.01.21

[buildozer]
log_level = 2
