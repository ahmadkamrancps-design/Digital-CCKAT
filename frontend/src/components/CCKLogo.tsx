import logoImage from "../assets/cck/logo.webp";

interface Props {
  size?: number;
}

export default function CCKLogo({ size = 52 }: Props) {
  return (
    <img
      src={logoImage}
      alt="Cadet College Kohat"
      width={size}
      height={size}
      style={{
        objectFit: "contain",
        backgroundColor: "var(--navy-dark, #001d3d)",
        borderRadius: 6,
        padding: 4,
      }}
    />
  );
}
