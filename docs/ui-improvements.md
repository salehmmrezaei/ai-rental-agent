# UI improvements and sample property photos

The existing Casa interface now uses generated interior photographs, clearer
search controls, an interactive gallery and actionable dashboard summaries. The
warm ivory and green branding, existing routes and backend permissions remain.

## Browsing and rental actions

- The homepage uses a generated apartment hero with direct room/apartment links,
  an optional-date hint, clearer search inputs and city shortcuts.
- Listing cards show photo counts, useful amenities, readable rent/availability
  and a direct View home link.
- Search has home-type shortcuts, removable filter chips, instant sorting and a
  collapsible mobile filter panel. Paired rental dates are removed together.
  Applying mobile filters closes the panel and returns to the results.
- Opening a result retains selected move-in/move-out dates. All homes returns
  to the previous search filters. Sign-in return links retain rental dates.
- Details have selectable thumbnails and a full photo viewer with previous/next
  controls, arrow-key navigation and Escape to close. Sample photos are labeled.
  The booking panel explains monthly rent, security deposit and the next step.
- Dashboard counts link to the related records. Tenants and the agency have an
  attention panel based on real pending requests, visits and unread messages.
  Navigation has clearer active states and closes with Escape on mobile.
- Property management cards use authenticated photo previews. Private images
  are still fetched with bearer headers and displayed through temporary blob URLs.

## Bundled demo images

Six images were generated with the built-in image-generation tool and exported
as WebP assets into `backend/app/demo_assets`. The homepage copy lives at
`frontend/src/assets/hero-living-v2.webp`. The source set and exact generation
prompts are documented in [the asset README](../backend/app/demo_assets/README.md).

The metadata import adds 1,200 sample image records to the 300 reserved demo
properties. Each property has an apartment photo, two room photos and a shared
kitchen. Room listings show their own room and the kitchen; apartment listings
show all four. The six generated images are reused across the synthetic portfolio.

Run the normal opt-in seed to create both data and photos:

```sh
docker compose --profile demo run --build --rm seed
```

For an existing complete demo database, attach only the photographs with:

```sh
docker compose exec backend python -m app.demo_images --demo
# Or against a migrated local database:
backend/.venv/bin/python -m app.demo_images --demo
```

The data and image imports are separate transactions; if the photo stage fails,
data stays intact and the CLI reports that the photo import should be retried.
Image import is idempotent, serialized with the demo seed lock, and preserves
uploaded images, existing captions and ordering. It touches only versioned demo
property IDs and refuses an incomplete or nonsynthetic portfolio.

Bundled assets are included in backend wheels and Docker images. Their metadata
uses unique record-specific storage keys; bytes resolve from the bundled asset
directory only after the existing image publication/ownership check passes.
No external image service or image-generation request runs when browsing. Normal
uploaded files keep their persistent storage behavior. Deleting sample metadata
does not delete the shared asset library; explicit reimport restores missing
sample records. No schema migration is needed. The authenticated property DTO adds
an optional `cover_image` using the normal authorized image URL.

## Verification

- Backend: 234 tests pass, including publication/ownership checks for bundled
  photos, room/gallery scoping, idempotency, preservation of uploads/captions,
  unsafe-key refusal and incomplete-import rollback.
- Frontend: strict production build and 36 tests pass, including date retention,
  paired-filter removal, instant sorting and keyboard gallery navigation.
- Chrome: all five tests pass against the isolated Docker stack. Added checks
  verify actual image decoding, mobile filter behavior, date retention, gallery
  controls, dashboard shortcuts and authenticated property covers. Automated
  WCAG checks pass on the homepage, listing detail, property cards and all agency
  routes; desktop/mobile screenshots are inspected.
- Existing lint warnings concern Fast Refresh exports and state in effects;
  the backend TestClient deprecation warning is unchanged.

Run `backend/.venv/bin/python -m app.verify` from the repository root for the
repeatable Docker, backend, frontend and browser verification workflow.
