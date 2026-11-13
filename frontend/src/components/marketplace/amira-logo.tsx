import Image from "next/image";

// The Amira wordmark with its arrow. The links around it carry the accessible name, so the image itself is decorative.
// "light" is the same logo with the wordmark in the light ink, for the dark auth panel.
export function AmiraLogo({ tone = "dark" }: { tone?: "dark" | "light" }) {
  return (
    <Image
      alt=""
      className="amira-logo"
      height={65}
      src={tone === "light" ? "/brand/amira-logo-light.png" : "/brand/amira-logo.png"}
      unoptimized
      width={157}
    />
  );
}
