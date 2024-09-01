import asyncio
import cProfile
import pstats


def profile_main():
    # Import the main script of your project
    import royals.launchers.launcher_leeching_v2 as main_script

    # Create a profiler
    profiler = cProfile.Profile()

    # Run the main script with the profiler
    profiler.enable()
    try:
        asyncio.run(main_script.main())
    except:
        pass
    profiler.disable()

    # Save the profiling data to a file
    # with open("profile_data.prof", "wb") as f:
    #     ps = pstats.Stats(profiler, stream=f)
    #     ps.sort_stats(pstats.SortKey.CUMULATIVE)
    profiler.dump_stats("profile_data.prof")
    # ps.print_stats()

    p = pstats.Stats("profile_data.prof")
    p.sort_stats(pstats.SortKey.CUMULATIVE).print_stats(20)
    breakpoint()


if __name__ == "__main__":
    profile_main()
