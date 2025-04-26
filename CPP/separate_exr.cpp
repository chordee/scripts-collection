#include <iostream>
#include <string>
#include <vector>
#include <filesystem>
#include <map>
#include <algorithm>

#include <OpenImageIO/imageio.h>
#include <OpenImageIO/imagebuf.h>
#include <OpenImageIO/imagebufalgo.h>

using namespace OIIO;

std::vector<std::string> split(const std::string &str, const std::string &delim)
{
    std::vector<std::string> result;
    size_t start = 0, end;
    while ((end = str.find(delim, start)) != std::string::npos)
    {
        result.push_back(str.substr(start, end - start));
        start = end + delim.length();
    }
    result.push_back(str.substr(start));
    return result;
}

void separate_exr(const std::string &filename, bool extBasename = false)
{
    OIIO::ImageBuf in(filename);
    std::filesystem::path path(filename);
    const std::filesystem::path source_file = path.filename();
    const auto source_names = split(source_file.string(), ".");

    if (!in.read())
    {
        std::cerr << "Failed to read: " << filename << std::endl;
        return;
    }

    const OIIO::ImageSpec &spec = in.spec();

    int xres = spec.width;
    int yres = spec.height;
    OIIO::TypeDesc format = spec.format;
    int nchannels = spec.nchannels;
    int pixels = xres * yres;
    std::map<std::string, std::vector<int>> channel_map;

    for (int i = 0; i < nchannels; ++i)
    {
        const std::string &ch_name = spec.channelnames[i];
        if (!ch_name.empty())
        {
            auto splitted = split(ch_name, ".");
            if (!splitted.empty())
            {
                auto iter = channel_map.find(splitted[0]);
                if (iter == channel_map.end())
                {
                    channel_map.insert({splitted[0], {i}});
                }
                else
                {
                    iter->second.push_back(i);
                }
            }
        }
    }

    auto p0 = std::find(spec.channelnames.begin(), spec.channelnames.end(), "R");
    auto p1 = std::find(spec.channelnames.begin(), spec.channelnames.end(), "G");
    auto p2 = std::find(spec.channelnames.begin(), spec.channelnames.end(), "B");
    auto p3 = std::find(spec.channelnames.begin(), spec.channelnames.end(), "A");
    if (p0 != spec.channelnames.end() && p1 != spec.channelnames.end() && p2 != spec.channelnames.end())
    {
        std::vector<int> tmp = {
            static_cast<int>(std::distance(spec.channelnames.begin(), p0)),
            static_cast<int>(std::distance(spec.channelnames.begin(), p1)),
            static_cast<int>(std::distance(spec.channelnames.begin(), p2))};
        if (p3 != spec.channelnames.end())
        {
            tmp.push_back(static_cast<int>(std::distance(spec.channelnames.begin(), p3)));
        }
        channel_map["beauty"] = tmp;
    }

    for (auto &it : channel_map)
    {
        if (it.second.size() > 1)
        {
            auto dir = path.parent_path() / it.first;
            std::filesystem::create_directories(dir);
            std::filesystem::path dst;
            if (source_names.size() < 2)
            {
                std::cerr << "Invalid filename format: " << source_file << std::endl;
                continue;
            }
            if (!extBasename)
            {
                dst = dir / (source_names[0] + "." + source_names[1]);
            }
            else
            {
                dst = dir / (source_names[0] + "_" + it.first + "." + source_names[1]);
            }
            OIIO::ImageBuf out;
            std::vector<int> order;
            if (it.second.size() == 3)
            {
                if (it.first == "N")
                {
                    auto np0 = std::find(spec.channelnames.begin(), spec.channelnames.end(), "N.x");
                    auto np1 = std::find(spec.channelnames.begin(), spec.channelnames.end(), "N.y");
                    auto np2 = std::find(spec.channelnames.begin(), spec.channelnames.end(), "N.z");
                    if (np0 != spec.channelnames.end() && np1 != spec.channelnames.end() && np2 != spec.channelnames.end())
                    {
                        order = {
                            static_cast<int>(std::distance(spec.channelnames.begin(), np0)),
                            static_cast<int>(std::distance(spec.channelnames.begin(), np1)),
                            static_cast<int>(std::distance(spec.channelnames.begin(), np2))};
                    }
                    else
                    {
                        order = it.second;
                    }
                }
                else
                {
                    order = it.second;
                }
                const char *names[] = {"R", "G", "B"};
                float values[] = {0, 0, 0};
                OIIO::ImageBufAlgo::channels(out, in, 3, order.data(), values, names);
                out.write(dst.string());
            }
            else if (it.second.size() == 4)
            {
                order = it.second;
                const char *names[] = {"R", "G", "B", "A"};
                float values[] = {0, 0, 0, 0};
                OIIO::ImageBufAlgo::channels(out, in, 4, order.data(), values, names);
                out.write(dst.string());
            }
        }
    }

    auto z = std::find(spec.channelnames.begin(), spec.channelnames.end(), "Z");
    if (z == spec.channelnames.end())
    {
        return;
    }
    else
    {
        int z_channel[] = {static_cast<int>(std::distance(spec.channelnames.begin(), z))};
        float values[] = {0};
        const char *names[] = {"Z"};

        OIIO::ImageBuf out;
        OIIO::ImageBufAlgo::channels(out, in, 1, z_channel, values, names);

        auto dir = path.parent_path() / "depth";
        std::filesystem::create_directories(dir);
        std::filesystem::path dst;

        if (source_names.size() < 2)
        {
            std::cerr << "Invalid filename format: " << source_file << std::endl;
            return;
        }
        if (!extBasename)
        {
            dst = dir / (source_names[0] + "." + source_names[1]);
        }
        else
        {
            dst = dir / (source_names[0] + "_depth." + source_names[1]);
        }
        bool ok = out.write(dst.string());
        if (!ok)
        {
            std::cerr << "Failed to write depth image: " << dst << std::endl;
        }
    }
}

int main(int argc, char **argv)
{
    std::vector<std::string> v_argv(argv, argv + argc);

    bool extbase = false;
    auto ptr = std::find(v_argv.begin(), v_argv.end(), "-extBase");

    if (ptr != v_argv.end())
        extbase = true;

    for (int i = 1; i < argc; i++)
    {
        std::filesystem::path path(v_argv[i]);
        if (std::filesystem::exists(path))
        {
            if (!std::filesystem::is_directory(path))
            {
                std::cout << path.extension() << std::endl;
                if (path.extension() == ".exr")
                {
                    separate_exr(std::filesystem::absolute(path).string(), extbase);
                }
            }
            else
            {
                for (auto &it : std::filesystem::directory_iterator(path))
                {
                    if (!std::filesystem::is_directory(it.path()) && it.path().extension() == ".exr")
                    {
                        separate_exr(std::filesystem::absolute(it.path()).string(), extbase);
                    }
                }
            }
        }
    }
    return 0;
}
