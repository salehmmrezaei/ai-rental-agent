import { useEffect, useState } from "react";
import { Building2 } from "lucide-react";
import { imageBlob, imageUrl } from "../api/client";
import { useAuth } from "../auth/AuthProvider";
import type { PropertyImage as ImageType } from "../api/types";

export function PropertyImage({
  image,
  privateImage = false,
  className = "",
}: {
  image?: ImageType;
  privateImage?: boolean;
  className?: string;
}) {
  const { epoch } = useAuth();
  const [loaded, setLoaded] = useState<{ key: string; url: string } | null>(
    null,
  );
  const [failed, setFailed] = useState<string | null>(null);
  const key = `${image?.url}:${epoch}`;
  useEffect(() => {
    if (!image || !privateImage) return;
    const controller = new AbortController();
    let objectUrl: string | undefined;
    imageBlob(image.url, controller.signal)
      .then((blob) => {
        if (!controller.signal.aborted) {
          objectUrl = URL.createObjectURL(blob);
          setLoaded({ key, url: objectUrl });
        }
      })
      .catch(() => {
        if (!controller.signal.aborted) setFailed(key);
      });
    return () => {
      controller.abort();
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [image?.url, privateImage, key]);
  const url = privateImage
    ? loaded?.key === key
      ? loaded.url
      : ""
    : image
      ? imageUrl(image.url)
      : "";
  if (!image || failed === key || !url)
    return (
      <div className={`image-placeholder ${className}`}>
        <Building2 size={42} strokeWidth={1} aria-hidden="true" />
        <span>
          {!image
            ? "Photos not added"
            : failed === key
              ? "Photo unavailable"
              : "Loading photo…"}
        </span>
      </div>
    );
  return (
    <img
      className={className}
      src={url}
      alt={image.alt_text}
      loading="lazy"
      onError={() => setFailed(key)}
    />
  );
}
