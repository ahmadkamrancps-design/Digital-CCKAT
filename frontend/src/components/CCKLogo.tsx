interface Props {
  size?: number;
}

export default function CCKLogo({ size = 52 }: Props) {
  return (
    <img
      src="/assets/cck/logo.png"
      alt="Cadet College Kohat"
      width={size}
      height={size}
      style={{
        objectFit: "contain",
      }}
    />
  );
}
