"""Example usage for the refactored AC_Design_Toolbox package."""

from pathlib import Path

from ac_design_toolbox.api import AVLCaseConfig, build_simple_aircraft, prepare_avl_airplane, run_case
from ac_design_toolbox.atmosphere import standard_atmosphere


def main() -> None:
    """Build a simple airplane, write AVL geometry, and run one operating point."""
    atmosphere = standard_atmosphere(altitude=1000.0, units="si", temp_shift_F=0.0)

    airplane = build_simple_aircraft(
        name="Example Aircraft",
        xyz_ref=(0.3, 0.0, 0.0),
        b_w=3.0,
        S_w=1.0,
        lambda_w=0.7,
        gamma_LE_w=5.0,
        span_frac_aileron=(0.65, 0.95),
        b_ht=1.2,
        S_ht=0.25,
        lambda_ht=0.8,
        L_ht=1.3,
        b_vt=0.7,
        S_vt=0.15,
        lambda_vt=0.8,
        L_vt=1.2,
        make_simple_fuselage=True,
    )

    working_directory = Path("example_runs")
    prepared = prepare_avl_airplane(airplane=airplane, working_directory=working_directory / "example_case")

    case = AVLCaseConfig(
        case_name="example_case",
        alpha=3.0,
        velocity=22.0,
        density=atmosphere["rho"],
    )

    results = run_case(
        airplane=airplane,
        avl_exe=Path("avl.exe"),
        working_directory=working_directory,
        config=case,
        control_index_map=prepared["control_index_map"],
        write_geom=False,
    )

    print(results["scalars"].get("CL"))


if __name__ == "__main__":
    main()
