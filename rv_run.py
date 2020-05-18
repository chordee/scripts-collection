import os

PROGRAM_FILES = 'C:/Program Files'
RV_VER = '0.0'


def main():
    try:
        if 'Shotgun' in os.listdir(PROGRAM_FILES):
            rv_dirs = os.listdir('/'.join([PROGRAM_FILES, 'Shotgun']))
            if len(rv_dirs) > 0:
                rv_run = '/'.join([PROGRAM_FILES, 'Shotgun', rv_dirs[-1], 'bin', 'rv.exe'])
                if os.path.exists(rv_run) is True:
                    RV_VER = rv_dirs[-1][3:]
                    os.system('"' + rv_run.replace('/', '\\') + '"')
                else:
                    raise EnvironmentError('Execute not Found.')
            else:
                raise EnvironmentError('RV Directory not Found.')
        else:
            raise EnvironmentError('Shotgun RV not Installed.')
    except EnvironmentError as err:
        print(err)

if __name__ == "__main__":
    main()
