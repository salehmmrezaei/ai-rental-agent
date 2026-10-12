import { useState } from "react";
import { Link, NavLink, Outlet } from "react-router-dom";
import { ArrowUpRight, Menu, X, House } from "lucide-react";
import { useAuth, dashboardPath } from "../auth/AuthProvider";
export function Brand() {
  return (
    <Link className="brand" to="/" aria-label="Casa homepage">
      <span className="brand-symbol">
        <House size={20} strokeWidth={1.8} />
      </span>
      casa<span className="brand-period">.</span>
    </Link>
  );
}
export function PublicLayout() {
  const { user } = useAuth();
  const [open, setOpen] = useState(false);
  return (
    <div className="public-layout">
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <header className="public-header">
        <div className="container nav-wrap">
          <Brand />
          <button
            className="icon-button mobile-menu"
            onClick={() => setOpen(!open)}
            aria-label="Toggle navigation"
            aria-expanded={open}
          >
            {open ? <X /> : <Menu />}
          </button>
          <nav
            className={open ? "public-nav open" : "public-nav"}
            aria-label="Main navigation"
            onClick={() => setOpen(false)}
          >
            <NavLink to="/listings">Find a home</NavLink>
            <NavLink to="/register?role=landlord">For landlords</NavLink>
            {user ? (
              <Link className="btn btn-primary" to={dashboardPath(user.role)}>
                My dashboard
                <ArrowUpRight size={16} />
              </Link>
            ) : (
              <>
                <Link to="/login">Log in</Link>
                <Link className="btn btn-primary" to="/register">
                  Get started
                  <ArrowUpRight size={16} />
                </Link>
              </>
            )}
          </nav>
        </div>
      </header>
      <main id="main">
        <Outlet />
      </main>
      <footer className="public-footer container">
        <div>
          <Brand />
          <p>A place to live. Room to grow.</p>
        </div>
        <div>
          <Link to="/listings">Explore homes</Link>
          <Link to="/register?role=landlord">List your property</Link>
          <Link to="/login">Your account</Link>
        </div>
        <p className="footer-note">
          Made for life in Italy.
          <br />
          Development properties are synthetic.
        </p>
      </footer>
    </div>
  );
}
