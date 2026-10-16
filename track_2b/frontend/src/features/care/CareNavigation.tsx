import { NavLink } from "react-router-dom";
export default function CareNavigation() {
  return (
    <nav className="care-navigation" aria-label="My Care sections">
      <NavLink to="../care/concerns">Health concerns</NavLink>
      <NavLink to="../care/team">Care Team</NavLink>
      <NavLink to="../care/visits">Records for a visit</NavLink>
    </nav>
  );
}
