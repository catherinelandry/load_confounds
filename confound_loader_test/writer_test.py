from load_confounds import load_confounds
from itertools import compress, product


def combinations(items):
    return (
        ",".join(list(compress(items, mask)))
        for mask in product(*[[0, 1]] * len(items))
    )


strategy_list = ["motion", "high_pass_filter", "matter", "compcor"]
strategies = list(combinations(strategy_list))[1:]
n_components = {"0.50", "0.80", "0.95"}
motion_models = ["6params", "derivatives", "square", "full"]

with open("test_confound_loader.py", "w") as test_writer:

    test_writer.write("from load_confounds import load_confounds \n")

    for strat in strategies:
        if "," in strat:
            strat_in = strat.split(",")
            strat_in_str = str(strat_in)[1:-1]
        else:
            strat_in_str = '''"''' + strat + '''"'''
            strat_in = [strat]

        for motion in motion_models:

            if "," in motion:
                motion_in = motion.split(",")
                motion_in_str = str(motion_in)[1:-1]
            else:
                motion_in_str = '''"''' + motion + '''"'''
                motion_in = motion

            for comp in n_components:

                if "," in comp:
                    comp_in = comp.split(",")
                    comp_in_str = str(comp_in)[1:-1]
                else:
                    comp_in_str = str(comp)
                    comp_in = float(comp)

                print("strat = ", strat)
                print("moition = ", motion)
                print("n_component = ", comp)
                print(" ")

                confound_raw = "sub-01_ses-001.tsv"
                confound_raw = '''"''' + confound_raw + '''"'''

                function_name = "def test_confound_loader_%s_%s_%s(): \n" % (
                    strat.replace("-", "").replace(",", ""),
                    motion.replace("-", "").replace(",", ""),
                    comp.replace("0.", ""),
                )

                function_test = (
                    "load_confounds(confounds_raw = %s, strategy = [%s], motion_model = %s, n_components = %s).columns.values"
                    % (confound_raw, strat_in_str, motion_in_str, comp_in_str)
                )

                function_out = str(
                    list(
                        load_confounds(
                            "sub-01_ses-001.tsv",
                            strategy=strat_in,
                            motion_model=motion_in,
                            n_components=comp_in,
                        ).columns
                    )
                )

                test_writer.write(function_name)
                test_writer.write("  assert ")

                test_writer.write("set(" + function_test + ")")
                test_writer.write(" == ")
                test_writer.write("set(" + function_out + ")")
                test_writer.write("\n")
                test_writer.write("\n\n")
