#include <iostream>
#include <string>
#include <vector>
#include <typeinfo>
#include <filesystem>
#include <map>

#include <OpenImageIO/imageio.h>
#include <OpenImageIO/imagebuf.h>
#include <OpenImageIO/imagebufalgo.h>

using namespace OIIO;
using namespace std;
using namespace ImageBufAlgo;

vector<string> split(const string &str, string delim){
    vector<string> result;
    string::size_type pos = str.find(delim);
    result.push_back(str.substr(0, pos));
    result.push_back(str.substr(pos+1));
    return result;
};

void separate_exr(const string &filename, bool extBasename = 0){
        ImageBuf &in = ImageBuf(filename);
        filesystem::path &path = filesystem::path(filename);
        const filesystem::path &source_file = path.filename();
        const auto source_names = split(source_file.string(), ".");

        if(!in.read())
            return;

        const ImageSpec &spec = in.spec();

        int xres = spec.width;
        int yres = spec.height;
        TypeDesc format = spec.format;
        int nchannels = spec.nchannels;
        int pixels = xres * yres;
        map<string, vector<int>> channel_map;

        for(int i = 0; i < nchannels; ++i){
            const string &ch_name = spec.channelnames[i];
            if(ch_name.size() > 0){
                auto splitted = split(ch_name, ".");
                auto iter = channel_map.find(splitted[0]);
                if(iter == channel_map.end()){
                    channel_map.insert(pair<string, vector<int>>(splitted[0], {i}));
                }
                else{
                    channel_map[splitted[0]].push_back(i);
                }
            }
        }
        auto p0 = find(spec.channelnames.begin(), spec.channelnames.end(), "R");
        auto p1 = find(spec.channelnames.begin(), spec.channelnames.end(), "G");
        auto p2 = find(spec.channelnames.begin(), spec.channelnames.end(), "B");
        auto p3 = find(spec.channelnames.begin(), spec.channelnames.end(), "A");
        if(p3 == spec.channelnames.end()){ 
            vector<int> tmp = {(int)distance(spec.channelnames.begin(), p0), (int)distance(spec.channelnames.begin(), p1), (int)distance(spec.channelnames.begin(), p2)};
            channel_map["beauty"] = tmp;
        }else{
            vector<int> tmp = {(int)distance(spec.channelnames.begin(), p0), (int)distance(spec.channelnames.begin(), p1), (int)distance(spec.channelnames.begin(), p2), (int)distance(spec.channelnames.begin(), p3)};
            channel_map["beauty"] = tmp;
        }
        for(auto &it : channel_map){
            if(it.second.size() > 1){
                auto dir = path.parent_path().append(it.first);
                filesystem::create_directory(dir);
                filesystem::path dst;
                if(extBasename == 0){
                    dst = dir.append(source_names[0] + "." + source_names[1]);
                }else{
                    dst = dir.append(source_names[0] + "_" + it.first + "." + source_names[1]);
                }
                ImageBuf out;
                int *order;
                if(it.second.size() == 3){
                    if(it.first == "N"){
                        auto p0 = find(spec.channelnames.begin(), spec.channelnames.end(), "N.x");
                        auto p1 = find(spec.channelnames.begin(), spec.channelnames.end(), "N.y");
                        auto p2 = find(spec.channelnames.begin(), spec.channelnames.end(), "N.z");
                        int tmp[] = {(int)distance(spec.channelnames.begin(), p0), (int)distance(spec.channelnames.begin(), p1), (int)distance(spec.channelnames.begin(), p2)};
                        order = &tmp[0];
                    }else{
                        order = &(it.second[0]);
                    }
                    string names[] = {"R", "G", "B"};
                    float values[] = {0, 0, 0};
                    ImageBufAlgo::channels(out, in, 3, order, values, names);
                    out.write(dst.string());
                }else if(it.second.size() == 4){
                    order = &(it.second[0]);
                    string names[] = {"R", "G", "B", "A"};
                    float values[] = {0, 0, 0, 0};
                    ImageBufAlgo::channels(out, in, 4, order, values, names);
                    out.write(dst.string());
                }
            }
        }
        auto z = find(spec.channelnames.begin(), spec.channelnames.end(), "Z");
        if(z == spec.channelnames.end()){
            return;
        }else{
            int z_channel[] = {spec.z_channel};     
            float values[] = {0};
            string names[] = {"Z"};

            ImageBuf out;
            ImageBufAlgo::channels(out, in, 1, z_channel, values, names);

            auto dir = path.parent_path().append("depth");
            filesystem::create_directory(dir);
            filesystem::path dst;

            
            if(extBasename == 0){
                dst = dir.append(source_names[0] + "." + source_names[1]);
            }else{
                dst = dir.append(source_names[0] + "_depth." + source_names[1]);
            }
            bool ok = out.write(dst.string());
        }
};

int main(int argc, char **argv){
    vector<string> v_argv(argv, argv + argc);
    
    int extbase = 0;
    auto ptr = find(v_argv.begin(), v_argv.end(), "-extBase");

    if(ptr != v_argv.end())
        extbase = 1;

    for(int i = 1; i < argc; i++){
        filesystem::path path(v_argv[i]);
        if(filesystem::exists(path)){
            if(!filesystem::is_directory(path)){
                cout << path.extension() << endl;
                if(path.extension() == ".exr"){
                    separate_exr(filesystem::absolute(path).string(), extbase);
                }
            }else{
                for(auto &it : filesystem::directory_iterator(path)){
                    if(!filesystem::is_directory(it.path()) && it.path().extension() == ".exr"){
                        separate_exr(filesystem::absolute(it.path()).string(), extbase);
                    }
                }
            }
            
        }
    }
    return 0;
}