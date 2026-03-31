using System;
using System.Collections.Generic;

[Serializable]
public class GameMessage
{
    public string type;
    public string payload;
}

[Serializable]
public class SetStatePayload
{
    public string state;
}

[Serializable]
public class PlayReactionPayload
{
    public string emotion;
    public string dialogue;
}

[Serializable]
public class SendMessageFormat
{
    public string type;
    public string payload;
}

public static class GameEvents
{
    public static event Action<SetStatePayload> OnSetState;
    public static event Action<PlayReactionPayload> OnPlayReaction;

    public static void FireSetState(SetStatePayload payload) => OnSetState?.Invoke(payload);
    public static void FirePlayReaction(PlayReactionPayload payload) => OnPlayReaction?.Invoke(payload);
}

public static class GlobalVariables
{
    public static List<PlayReactionPayload> ReactionQueue = new List<PlayReactionPayload>();
    public static int VoiceState = 0;
    public static int[] CurrentBoard = new int[9];
    public static bool IsGameActive = false;
    public static string CurrentState = "idle";
}

public enum Emotion
{
    normal,
    happy,
    angry,
    sad,
    surprised,
    shy,
    excited,
    smug,
    calm,
    waiting
}

public enum QuQuMorph
{
    komaru = 4,
    hohozome = 5,
    koukakuage = 7,
    bikkuri = 8,
    okori = 9,
    nikori = 10,
    mayu_ue = 11,
    mayu_sita = 12,
    mabataki = 13,
    zitome = 14,
    niramu = 15,
    hitomi_small = 16,
    hitomi_large = 17,
    nagomi = 19,
    ee = 21,
    pero = 22,
    warai = 43,
    niyari = 44,
    wink_left = 45,
    wink_right = 46,
    heart = 49,
    star = 50,
    high_light_off = 52,
}
