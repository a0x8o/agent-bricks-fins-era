import onDark1x from "../../assets/brand/youcom-on-dark@1x.png";
import onDark2x from "../../assets/brand/youcom-on-dark@2x.png";
import onDark3x from "../../assets/brand/youcom-on-dark@3x.png";
import onLight1x from "../../assets/brand/youcom-on-light@1x.png";
import onLight2x from "../../assets/brand/youcom-on-light@2x.png";
import onLight3x from "../../assets/brand/youcom-on-light@3x.png";
import mark20 from "../../assets/brand/youcom-mark-20.png";
import mark64 from "../../assets/brand/youcom-mark-64.png";
import { useApp } from "../../stores/app";

/** You.com brand lockup — theme-aware wordmark, mark-only variant for narrow views. */
export function BrandLogo({ variant = "full" }: { variant?: "full" | "mark" }) {
  const theme = useApp((s) => s.theme);
  if (variant === "mark") {
    return (
      <img src={mark20} srcSet={`${mark64} 3.2x`} width={20} height={20} alt="You.com" className="block" />
    );
  }
  const src = theme === "dark" ? onDark1x : onLight1x;
  const srcSet = theme === "dark"
    ? `${onDark1x} 1x, ${onDark2x} 2x, ${onDark3x} 3x`
    : `${onLight1x} 1x, ${onLight2x} 2x, ${onLight3x} 3x`;
  return <img src={src} srcSet={srcSet} width={77} height={20} alt="You.com" className="block" />;
}
