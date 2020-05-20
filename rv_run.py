import os, sys

PROGRAM_FILES = 'C:/Program Files'
os.environ['RV_SUPPORT_PATH'] = 'Q:\\Resource\\rv\\plugins'

def main(dark = False):
    try:
        if 'Shotgun' in os.listdir(PROGRAM_FILES):
            rv_dirs = os.listdir('/'.join([PROGRAM_FILES, 'Shotgun']))
            if len(rv_dirs) > 0:
                rv_dirs.sort()
                rv_run = '/'.join([PROGRAM_FILES, 'Shotgun', rv_dirs[-1], 'bin', 'rv.exe'])
                if os.path.exists(rv_run) is True:
                    cmd = '"' + rv_run.replace('/', '\\') + '"'
                    if dark is False:
                        os.system(cmd)
                    else:
                        os.system(cmd + ' -qtstyle fusion -qtcss Q:\\Resource\\rv\\darkorange.qss')
                else:
                    raise EnvironmentError('Execute not Found.')
            else:
                raise EnvironmentError('RV Directory not Found.')
        else:
            raise EnvironmentError('Shotgun RV not Installed.')
    except EnvironmentError as err:
        print(err)

if __name__ == "__main__":
    if len(sys.argv) > 1:
        if sys.argv[1] == '-dark':
            main(dark = True)
    else:
        main()
