# TD Miner Android

Command-line Android build. No Android Studio required.

## Build

```powershell
.\gradlew.bat testDebugUnitTest assembleDebug
```

APK:

```text
app/build/outputs/apk/debug/app-debug.apk
```

## Install To Phone

Enable USB debugging, then:

```powershell
$adb = "$env:LOCALAPPDATA\Android\Sdk\platform-tools\adb.exe"
& $adb devices
& $adb install -r app\build\outputs\apk\debug\app-debug.apk
& $adb shell am start -n io.github.himanm.tdminer/.MainActivity
```

## Seed Desktop Cookies For Debug Testing

Do not bake cookies into the APK. For local testing, copy the existing desktop JSON cookie jar into the app-private files directory:

```powershell
& $adb push ..\dist\cookies.jar /sdcard/Download/tdminer-cookies.jar
& $adb shell run-as io.github.himanm.tdminer sh -c "mkdir -p files && cp /sdcard/Download/tdminer-cookies.jar files/cookies.jar"
& $adb shell am start -n io.github.himanm.tdminer/.MainActivity
```

The app stores imported cookies in private `SharedPreferences`. They survive `adb install -r` updates and are cleared by Logout or app uninstall.

The current app is a native responsive shell only. It does not run the real miner core yet.
