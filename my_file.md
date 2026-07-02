Deleting a file that a documented invariant protects, that the default config points at, the night before launch — is exactly the kind of thing I shouldn't just do. Recommendation: for the pilot, don't run it and don't delete it. Just set IMAGE_SERVER_URL=https://api.teampop.<tld> so images resolve through onboarding's /images mount. That gives you exactly what you want (no :8000 process) with zero risk. The actual deletion + config-default fix + doc/invariant cleanup is a clean post-pilot commit — I can do it properly then.

(One thing to align on the box: make sure STORE_IMAGES_PATH and the mount both point at onboarding-service/images/ so downloaded images are the ones served.)


13.232.36.194

