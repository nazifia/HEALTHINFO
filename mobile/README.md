# health_info_app

A new Flutter project.

## Getting Started

This project is a starting point for a Flutter application.

A few resources to get you started if this is your first Flutter project:

- [Learn Flutter](https://docs.flutter.dev/get-started/learn-flutter)
- [Write your first Flutter app](https://docs.flutter.dev/get-started/codelab)
- [Flutter learning resources](https://docs.flutter.dev/reference/learning-resources)

For help getting started with Flutter development, view the
[online documentation](https://docs.flutter.dev/), which offers tutorials,
samples, guidance on mobile development, and a full API reference.

## Build and deploy the web build

This directory holds the Flutter app. Its web build is a *different* frontend from
the static SPA in `web/`, and the two have one Firebase project each:

| Directory | Project | What it serves |
| --- | --- | --- |
| `mobile/` | `healthinfoapp2` | the Flutter web build (`build/web`) |
| `web/` | `healthinfoweb` | the static HTML/CSS/JS SPA |

```bash
cd mobile
flutter build web --release
firebase deploy
```

A `predeploy` hook in `firebase.json` refuses the deploy unless the target project
is `healthinfoapp2`/`healthinfoapp` and `build/web/main.dart.js` exists, so
`firebase deploy -P healthinfoweb` from here cannot push the Flutter build over the
static site — which is how both URLs once served the same frontend. Never add
`healthinfoweb` to `.firebaserc` here.

Mobile builds (`flutter build apk`, `flutter build ipa`) are unaffected; the guard
only runs on `firebase deploy`.
