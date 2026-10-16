import { NavLink } from "react-router-dom";
import "./care-navigation.css";
export default function CareNavigation() {
  return (
    <nav
      className="care-navigation care-navigation--compact"
      aria-label="My Care sections"
    >
      <NavLink to="../care/concerns">Health concerns</NavLink>
      <NavLink to="../care/team">Care Team</NavLink>
      <NavLink to="../care/visits">Prepare for a visit</NavLink>
    </nav>
  );
}
