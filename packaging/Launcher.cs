using System;
using System.Diagnostics;
using System.IO;
using System.IO.Compression;
using System.Reflection;
using System.Security.Cryptography;

// A Windows bootstrapper. Payload contains only allowlisted application files.
class Launcher
{
    static int Main(string[] args)
    {
        try
        {
            byte[] payload;
            using (var stream = Assembly.GetExecutingAssembly().GetManifestResourceStream("payload.zip"))
            using (var memory = new MemoryStream()) { stream.CopyTo(memory); payload = memory.ToArray(); }
            string digest;
            using (var sha = SHA256.Create()) { digest = BitConverter.ToString(sha.ComputeHash(payload)).Replace("-", "").ToLowerInvariant(); }
            string version;
            using (var archive = new ZipArchive(new MemoryStream(payload)))
            using (var reader = new StreamReader(archive.GetEntry("VERSION").Open())) { version = reader.ReadToEnd().Trim(); }
            bool extractOnly = args.Length == 2 && args[0] == "--extract-only";
            if (args.Length != 0 && !extractOnly) throw new ArgumentException("Usage: setup.exe [--extract-only <empty directory>]");
            var root = Path.GetFullPath(extractOnly ? args[1] : Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "GameHarness", "apps", version + "-" + digest.Substring(0, 12)));
            if (extractOnly && Directory.Exists(root) && Directory.GetFileSystemEntries(root).Length > 0)
                throw new IOException("Extract-only requires an empty directory.");
            Directory.CreateDirectory(root);
            using (var archive = new ZipArchive(new MemoryStream(payload)))
            {
                foreach (var entry in archive.Entries)
                {
                    var target = Path.GetFullPath(Path.Combine(root, entry.FullName.Replace('/', Path.DirectorySeparatorChar)));
                    if (!target.StartsWith(root + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase))
                        throw new IOException("Invalid package path.");
                    if (entry.FullName.EndsWith("/")) continue;
                    Directory.CreateDirectory(Path.GetDirectoryName(target));
                    // A build has its own directory. Existing projects and databases live elsewhere.
                    using (var source = entry.Open())
                    using (var output = File.Create(target)) { source.CopyTo(output); }
                }
            }
            File.WriteAllText(Path.Combine(root, ".installed"), version);
            Console.WriteLine("Codex Vibe Game Creator " + version);
            Console.WriteLine(root);
            if (extractOnly) return 0;
            var start = new ProcessStartInfo("powershell.exe",
                "-NoProfile -ExecutionPolicy Bypass -File \"" + Path.Combine(root, "start.ps1") + "\"");
            start.WorkingDirectory = root;
            start.UseShellExecute = false;
            using (var process = Process.Start(start))
            {
                process.WaitForExit();
                if (process.ExitCode != 0) { Console.WriteLine("Setup did not complete. Press Enter to close, then run setup again to retry."); Console.ReadLine(); }
                return process.ExitCode;
            }
        }
        catch (Exception error)
        {
            Console.Error.WriteLine(error.Message);
            if (args.Length == 0) { Console.WriteLine("Press Enter to close."); Console.ReadLine(); }
            return 1;
        }
    }
}
