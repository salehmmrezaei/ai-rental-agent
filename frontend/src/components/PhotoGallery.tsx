import { useEffect, useState } from "react";
import { ChevronLeft, ChevronRight, Expand, Images } from "lucide-react";
import type { PropertyImage as Photo } from "../api/types";
import { PropertyImage } from "./PropertyImage";
import { Button, Modal } from "./ui";

export function PhotoGallery({ images }: { images: Photo[] }) {
  const [selected, setSelected] = useState(0);
  const [open, setOpen] = useState(false);
  const current = images[selected];
  useEffect(() => {
    if (!open || images.length < 2) return;
    function keys(event: KeyboardEvent) {
      if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
      event.preventDefault();
      setSelected(
        (value) =>
          (value + (event.key === "ArrowLeft" ? -1 : 1) + images.length) %
          images.length,
      );
    }
    window.addEventListener("keydown", keys);
    return () => window.removeEventListener("keydown", keys);
  }, [open, images.length]);
  if (!images.length)
    return (
      <div className="photo-gallery">
        <PropertyImage />
      </div>
    );
  return (
    <>
      <div className="photo-gallery">
        <button
          className="gallery-feature"
          type="button"
          aria-label={`View photo ${selected + 1} of ${images.length}`}
          onClick={() => setOpen(true)}
        >
          <PropertyImage image={current} eager />
          <span className="gallery-expand">
            <Expand size={16} />
            View photos
          </span>
          <span className="gallery-counter">
            <Images size={15} />
            {selected + 1} / {images.length}
          </span>
        </button>
        {images.length > 1 && (
          <div className="gallery-thumbnails" aria-label="Choose a photo">
            {images.map((photo, index) => (
              <button
                key={photo.id}
                type="button"
                aria-label={`Show photo ${index + 1}`}
                aria-pressed={selected === index}
                onClick={() => setSelected(index)}
              >
                <span aria-hidden="true">
                  <PropertyImage image={photo} />
                </span>
              </button>
            ))}
          </div>
        )}
      </div>
      {open && (
        <Modal title="Photos of this home" onClose={() => setOpen(false)}>
          <div className="photo-viewer">
            <PropertyImage image={current} eager />
            <div className="photo-viewer-controls">
              <Button
                variant="secondary"
                disabled={images.length < 2}
                aria-label="Previous photo"
                onClick={() =>
                  setSelected((selected - 1 + images.length) % images.length)
                }
              >
                <ChevronLeft size={20} />
              </Button>
              <p>
                {selected + 1} of {images.length}
              </p>
              <Button
                variant="secondary"
                disabled={images.length < 2}
                aria-label="Next photo"
                onClick={() => setSelected((selected + 1) % images.length)}
              >
                <ChevronRight size={20} />
              </Button>
            </div>
            <p className="photo-caption">{current.alt_text}</p>
          </div>
        </Modal>
      )}
    </>
  );
}
